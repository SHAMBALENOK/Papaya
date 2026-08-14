import os
import pandas as pd
from huggingface_hub import InferenceClient, get_token
from huggingface_hub.errors import HfHubHTTPError
from app.database import events as db_events
from googletrans import Translator
import uuid as uuid_mod
from app.middlewares.task_queue import task_queue, AsyncCeleryTask, run_task
from app.middlewares.ai_filling.images import find_images

translator = Translator()

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

async def translate_text(text):
    """
    Translates text from russian to english
    """
    translator = Translator()
    result = await translator.translate(text, dest='en')
    return result.text

async def _classify(sentences: list) -> list:
    """
    Searches for a name in table headers and description
    """
    output = {}
    client = _get_client()

    for i, sentence in enumerate(sentences):
        try:
            data = client.zero_shot_classification(
                await translate_text(sentence),
                candidate_labels=LABELS,
            )
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
            raise

        # .get() совместимо и с новыми версиями huggingface_hub (dataclass+dict),
        # и со старыми (обычные dict)
        output[i] = data[0].get("score")

    name = (sentences.index(sentences[max(output, key=output.get)]) ,sentences.pop(max(output, key=output.get)))
    classified = list()
    classified.append(name)
    for i in sentences:
        classified.append((sentences.index(i), i))

    return classified

@task_queue.task(base=AsyncCeleryTask, time_limit=120, default_retry_delay=30, retry_backoff=True, retry_backoff_max=120, queue="heavy")
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
            pictures = await run_task(find_images, query=payload.get('name', 'null'))
            payload.update(pictures)
            created = await db_events.add_event(ins=payload)
            created_events.append(created)
    return created_events