import os
import asyncio
import inspect
import logging
import pandas as pd
from huggingface_hub import InferenceClient, get_token
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.utils import get_session
from app.database import events as db_events
import uuid as uuid_mod
from app.middlewares.task_queue import task_queue, AsyncCeleryTask, run_task
from app.middlewares.ai_filling.images import find_images

logger = logging.getLogger(__name__)

# googletrans — необязательная зависимость: её API несовместим с await
# (translate() в 4.0.0-rc1 синхронный), а пин httpx==0.13.3 конфликтует
# с huggingface_hub (httpx>=0.23). Основной перевод — модель на HF.
try:
    from googletrans import Translator as _GoogleTranslator
except Exception:  # библиотека не установлена или не импортируется
    _GoogleTranslator = None

MODEL_ID = "facebook/bart-large-mnli"
LABELS = ['olympiad']

# Загружаем переменные из .env, если приложение запущено не через Docker
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv может отсутствовать в минимальной установке
    pass

# Значения, которые явно означают "токен не настроен" (плейсхолдеры из шаблонов)
_PLACEHOLDER_TOKENS = {
    "", "your_secret_token", "your_token", "huggingface_token",
    "hf_xxx", "hf_token", "changeme",
}


def _get_hf_token() -> str:
    """
    Читает токен Hugging Face на момент вызова.

    Важно: токен читается при каждом запросе к Inference API, а не при
    импорте модуля. Иначе обновлённый HF_TOKEN не подхватится, пока процесс
    не перезапущен, и в Hugging Face будет уходить старый/неверный токен —
    ровно это выглядит как 401 "Invalid username or password".
    """
    token = (os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or "").strip()
    if token.lower() in _PLACEHOLDER_TOKENS:
        token = ""
    if not token:
        # Запасной вариант: токен, сохранённый через `hf auth login`.
        token = (get_token() or "").strip()
    if not token or token.lower() in _PLACEHOLDER_TOKENS:
        raise RuntimeError(
            "Hugging Face токен не настроен. Задайте переменную окружения "
            "HF_TOKEN (read-токен или fine-grained токен с разрешением "
            "\"Make calls to Inference Providers\") и перезапустите сервис. "
            "Создать токен: https://huggingface.co/settings/tokens"
        )
    return token


def _get_client() -> InferenceClient:
    """Создаёт клиент Inference API с актуальным токеном из окружения."""
    return InferenceClient(model=MODEL_ID, token=_get_hf_token())

HF_TRANSLATION_MODEL = "Helsinki-NLP/opus-mt-ru-en"

# URL классического hf-inference маршрута (совпадает с тем, что использует
# InferenceClient): используется для резервного прямого запроса.
ZERO_SHOT_URL = f"https://router.huggingface.co/hf-inference/models/{MODEL_ID}"


def _raw_zero_shot_scores(text: str) -> list[float]:
    """
    Прямой запрос к HF Inference API в обход высокоуровневого метода.

    Нужен как резервный путь: в версиях huggingface_hub <1.2.0 метод
    zero_shot_classification() сломан — библиотека ждёт от сервера dict,
    а сервер возвращает list, из-за чего возникает
    "TypeError: list indices must be integers or slices, not str".

    Разбор ответа сделан устойчивым: принимаем и список словарей
    [{"sequence": ..., "labels": [...], "scores": [...]}], и одиночный dict.
    """
    response = get_session().post(
        ZERO_SHOT_URL,
        json={
            "inputs": text,
            "parameters": {"candidate_labels": LABELS},
        },
        headers={"Authorization": f"Bearer {_get_hf_token()}"},
        timeout=(10, 120),
    )
    if response.status_code == 401:
        raise RuntimeError(
            "Hugging Face отклонил токен (401 Unauthorized). "
            "Убедитесь, что HF_TOKEN содержит актуальный read-токен "
            "(или fine-grained токен с разрешением \"Make calls to "
            "Inference Providers\") и пересоздайте контейнеры/перезапустите "
            "воркер. Ответ Hugging Face: " + (response.text or "")[:300]
        )
    response.raise_for_status()

    payload = response.json()
    if isinstance(payload, (list, tuple)):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected zero-shot response: {payload!r}")

    scores = payload.get("scores")
    if not isinstance(scores, (list, tuple)) or not scores:
        score = payload.get("score")
        scores = [score] if score is not None else []
    if not scores:
        raise ValueError(f"No scores in zero-shot response: {payload!r}")
    return [float(s) for s in scores]


async def translate_text(text, hf_client: InferenceClient | None = None):
    """
    Translates text from russian to english.

    Порядок фолбэков:
    1) Google Translate (googletrans) — только если библиотека установлена;
    2) модель перевода на Hugging Face Inference API (Helsinki-NLP/opus-mt-ru-en)
       — использует тот же токен, что и классификация;
    3) исходный текст — перевод не должен ронять весь импорт.
    """
    if _GoogleTranslator is not None:
        try:
            # googletrans 4.0.0-rc1 синхронный — вызываем в потоке,
            # чтобы не блокировать event loop; форки с async API тоже поддержаны.
            result = await asyncio.to_thread(
                _GoogleTranslator().translate, text, dest='en'
            )
            if inspect.isawaitable(result):
                result = await result
            return result.text
        except Exception as e:
            logger.warning("Google translation failed (%s), trying HF model", e)

    if hf_client is not None:
        try:
            result = hf_client.translation(text, model=HF_TRANSLATION_MODEL)
            # Новые версии huggingface_hub возвращают объект TranslationOutput (dict),
            # старые — list[dict] с ключом translation_text.
            if isinstance(result, (list, tuple)):
                result = result[0] if result else {}
            if isinstance(result, dict):
                translated = result.get("translation_text")
            else:
                translated = getattr(result, "translation_text", None)
            if translated:
                return translated
        except Exception as e:
            logger.warning("HF translation failed (%s), using original text: %r", e, text)

    return text


def _extract_score(data) -> float:
    """
    Достаёт score из ответа zero-shot classification.

    Устойчиво к разным форматам ответа в разных версиях huggingface_hub:
    - list[ZeroShotClassificationOutputElement] (dataclass+dict) — новые версии;
    - list[dict] — версии 0.16-0.26;
    - dict с ключом 'scores' — совсем старые версии.
    """
    if isinstance(data, (list, tuple)):
        if not data:
            raise ValueError("Empty response from zero-shot classification")
        data = data[0]
    if isinstance(data, dict):
        score = data.get("score")
        if score is None:
            scores = data.get("scores")
            if isinstance(scores, (list, tuple)) and scores:
                score = scores[0]
        if score is None:
            raise ValueError(f"No 'score' in response: {data!r}")
        return float(score)
    score = getattr(data, "score", None)
    if score is None:
        raise ValueError(
            f"Unexpected response type {type(data).__name__}: {data!r}"
        )
    return float(score)


def _classify_one(client: InferenceClient, translated: str) -> float:
    """
    Возвращает score заголовка по метке LABELS[0].

    Сначала пробуем высокоуровневый zero_shot_classification(). В старых
    версиях huggingface_hub (<1.2.0) он падает с TypeError «list indices
    must be integers or slices, not str» из-за ошибки разбора ответа
    сервера — тогда делаем тот же запрос напрямую и разбираем ответ сами.
    """
    try:
        data = client.zero_shot_classification(translated, candidate_labels=LABELS)
        return _extract_score(data)
    except HfHubHTTPError:
        raise
    except Exception as first_error:
        logger.warning(
            "zero_shot_classification() failed (%s); trying raw request", first_error
        )
        try:
            scores = _raw_zero_shot_scores(translated)
        except Exception:
            # Резервный запрос не помог — пробрасываем исходную ошибку,
            # чтобы её обработал общий обработчик с полным трейсбеком.
            raise first_error
        return float(scores[0]) if scores else 0.0


async def _classify(sentences: list) -> list:
    """
    Searches for a name in table headers and description
    """
    output = {}
    client = _get_client()

    for i, sentence in enumerate(sentences):
        try:
            translated = await translate_text(sentence, hf_client=client)
            output[i] = _classify_one(client, translated)
            logger.info("header #%d score=%.3f (%r)", i, output[i], sentence)
        except HfHubHTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 401:
                raise RuntimeError(
                    "Hugging Face отклонил токен (401 Unauthorized). "
                    "Убедитесь, что HF_TOKEN содержит актуальный read-токен "
                    "(или fine-grained токен с разрешением \"Make calls to "
                    "Inference Providers\"), и пересоздайте контейнеры/"
                    "перезапустите воркер: токен читается при старте процесса. "
                    f"Ответ Hugging Face: {e}"
                ) from e
            logger.warning(
                "HF returned HTTP %s for header #%d %r; score set to 0",
                status, i, sentence,
            )
            output[i] = 0.0
        except RuntimeError:
            # Ошибки токена (401) из резервного запроса фатальны и не должны
            # маскироваться нулевым скорингом.
            raise
        except Exception as e:
            # Ошибка анализа одного заголовка не должна ронять весь импорт:
            # полный трейсбек попадает в лог, а столбец получит нулевой скоринг.
            logger.exception(
                "Classification failed for header #%d %r; score set to 0",
                i, sentence,
            )
            output[i] = 0.0

    if not output:
        raise ValueError("Таблица не содержит заголовков для анализа")

    name = (sentences.index(sentences[max(output, key=output.get)]) ,sentences.pop(max(output, key=output.get)))
    classified = list()
    classified.append(name)
    for i in sentences:
        classified.append((sentences.index(i), i))

    return classified

@task_queue.task(base=AsyncCeleryTask, time_limit=600, default_retry_delay=30, retry_backoff=True, retry_backoff_max=120, queue="heavy")
async def tabulate(xlsx_path: str, owner: str):
    """
    Converting information from an Excel table to SQL
    """
    file = pd.ExcelFile(xlsx_path).parse().ffill()
    created_events = []

    labels = await _classify([i.replace('\n', ' ') for i in file.columns])

    for row in file.itertuples():
        row_dict = row._asdict()
        payload = dict()
        # for i in range(0, len(row)):
        #     print(row[i])
        payload['disc'] = str()
        payload['owner'] = uuid_mod.UUID(owner)
        payload['name'] = row_dict.get("_"+str(labels[0][0]))
        formated_labels = labels[1:len(labels)]
        for i in formated_labels:
            value = row_dict.get("_"+str(i[0]+1))
            # Пустые/NaN ячейки не должны валить .replace()
            if isinstance(value, float) and pd.isna(value):
                value = ''
            else:
                value = str(value).replace(r"\n", " ")
            payload['disc'] += f'\n{i[1]}: {value}'

        if payload.get('name', 'null') != 'null':
            # Поиск картинок не должен ронять импорт: при сбое событие
            # создаётся без превью и фоновой картинки.
            try:
                pictures = await run_task(find_images, query=payload.get('name', 'null'))
                payload.update(pictures)
            except Exception as e:
                logger.warning(
                    "Image search failed for %r (%s); event will be created without pictures",
                    payload.get('name'), e,
                )
            created = await db_events.add_event(ins=payload)
            created_events.append(created)
    return created_events