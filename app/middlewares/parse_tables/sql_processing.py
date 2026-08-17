import asyncio
import os
import uuid as uuid_mod

import pandas as pd

from app.database import events as db_events
from app.middlewares.ai_filling.images import find_images


_NAME_MARKERS = (
    'назван',
    'наименован',
    'заголов',
    'name',
    'title',
)
_EVENT_MARKERS = (
    'олимпиад',
    'мероприят',
    'событ',
    'конкурс',
    'event',
    'olympiad',
    'competition',
)
_DESCRIPTION_MARKERS = (
    'профил',
    'предмет',
    'уров',
    'диплом',
    'результат',
    'направлен',
    'описан',
    'description',
    'subject',
    'level',
    'result',
)
_EMPTY_IMAGES = {
    'preview_picture': None,
    'picture': None,
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


IMPORT_IMAGES = _env_bool('TABLE_IMPORT_IMAGES', True)
IMAGE_SEARCH_TIMEOUT = _env_float('TABLE_IMAGE_TIMEOUT', 5.0)
IMAGE_SEARCH_CONCURRENCY = _env_int('TABLE_IMAGE_CONCURRENCY', 4)


def _header_score(header: str) -> int:
    """Оценить вероятность того, что колонка содержит название события."""
    normalized = ' '.join(str(header).casefold().replace('ё', 'е').split())

    # Явное «Название олимпиады»/"Event name" всегда приоритетнее других
    # колонок, в которых тоже может встречаться слово «олимпиада».
    score = 0
    if any(marker in normalized for marker in _NAME_MARKERS):
        score += 100
    if any(marker in normalized for marker in _EVENT_MARKERS):
        score += 30
    if any(marker in normalized for marker in _DESCRIPTION_MARKERS):
        score -= 40
    return score


def _classify(sentences: list[str]) -> list[tuple[int, str]]:
    """Найти колонку с названием без обращения к внешним API.

    Если заголовки неизвестного формата и ни один маркер не найден, первой
    колонкой с названием считается первая колонка таблицы.
    """
    if not sentences:
        raise ValueError('The table has no columns')

    name_index = max(
        range(len(sentences)),
        key=lambda index: _header_score(sentences[index]),
    )
    return [
        (name_index, sentences[name_index]),
        *(
            (index, sentence)
            for index, sentence in enumerate(sentences)
            if index != name_index
        ),
    ]


async def _find_images_with_limit(
    query: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, str | None]:
    """Ограничить время и число одновременных запросов изображений."""
    async with semaphore:
        try:
            return await asyncio.wait_for(
                find_images(query=query),
                timeout=IMAGE_SEARCH_TIMEOUT,
            )
        except TimeoutError:
            return dict(_EMPTY_IMAGES)


async def _enrich_with_images(payloads: list[dict]) -> None:
    """Опционально добавить картинки, не блокируя импорт последовательно."""
    if not IMPORT_IMAGES or not payloads:
        for payload in payloads:
            payload.update(_EMPTY_IMAGES)
        return

    semaphore = asyncio.Semaphore(IMAGE_SEARCH_CONCURRENCY)
    images = await asyncio.gather(
        *(
            _find_images_with_limit(payload['name'], semaphore)
            for payload in payloads
        )
    )
    for payload, event_images in zip(payloads, images):
        payload.update(event_images)


async def tabulate(xlsx_path: str, owner: str):
    """Преобразовать Excel-таблицу в события без запуска Celery-задачи.

    Допустимое время зависит от числа строк, поэтому обработка XLSX выполняется
    как обычная async-функция без Celery time limit. DDGS-картинки можно
    отключить через TABLE_IMPORT_IMAGES=false; события записываются одной
    транзакцией.
    """
    table = pd.ExcelFile(xlsx_path).parse().ffill()
    column_names = [str(column).replace('\n', ' ') for column in table.columns]
    labels = _classify(column_names)
    payloads = []

    for _, row in table.iterrows():
        name_value = row.iloc[labels[0][0]]
        if pd.isna(name_value):
            continue
        name = str(name_value).strip()
        if not name or name.casefold() == 'null':
            continue

        payload = {
            'disc': '',
            'owner': uuid_mod.UUID(owner),
            'name': name,
        }
        for column_index, column_name in labels[1:]:
            value = row.iloc[column_index]
            if pd.isna(value):
                value = ''
            else:
                value = str(value).replace(r'\n', ' ')
            payload['disc'] += f'\n{column_name}: {value}'
        payloads.append(payload)

    await _enrich_with_images(payloads)
    return await db_events.add_events(payloads)