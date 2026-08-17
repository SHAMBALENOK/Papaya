import asyncio
import logging
import os
from typing import Any

from ddgs import DDGS


logger = logging.getLogger(__name__)
_EMPTY_IMAGES = {
    'preview_picture': None,
    'picture': None,
}


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


DDGS_TIMEOUT = _env_float('DDGS_IMAGE_TIMEOUT', 4.0)
DDGS_MAX_RESULTS = _env_int('DDGS_IMAGE_RESULTS', 10)
DDGS_REGION = os.getenv('DDGS_IMAGE_REGION', 'ru-ru')
DDGS_BACKEND = os.getenv('DDGS_IMAGE_BACKEND', 'duckduckgo')
DDGS_PROXY = os.getenv('DDGS_PROXY') or None


def _dimensions(image: dict[str, Any]) -> tuple[float, float]:
    """Вернуть безопасные размеры результата DDGS."""
    try:
        width = float(image.get('width') or 0)
        height = float(image.get('height') or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    return width, height


def _ratio(image: dict[str, Any]) -> float:
    width, height = _dimensions(image)
    return width / height if width > 0 and height > 0 else 1.0


def _image_url(image: dict[str, Any], *, thumbnail: bool = False) -> str | None:
    """Извлечь URL изображения из структуры результата DDGS."""
    keys = ('thumbnail', 'image') if thumbnail else ('image', 'thumbnail')
    for key in keys:
        value = image.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _select_images(images: list[dict[str, Any]]) -> dict[str, str | None]:
    """Выбрать квадратное превью и наиболее широкую основную картинку."""
    usable = [
        image
        for image in images
        if isinstance(image, dict) and _image_url(image) is not None
    ]
    if not usable:
        return dict(_EMPTY_IMAGES)

    preview = min(usable, key=lambda image: abs(_ratio(image) - 1.0))
    wide_images = [image for image in usable if _ratio(image) > 1.0]
    picture = max(wide_images or usable, key=_ratio)

    return {
        'preview_picture': _image_url(preview, thumbnail=True),
        'picture': _image_url(picture),
    }


def _find_images_sync(query: str) -> dict[str, str | None]:
    """Выполнить синхронный DDGS-поиск; вызывается только в отдельном потоке."""
    with DDGS(proxy=DDGS_PROXY, timeout=DDGS_TIMEOUT) as client:
        results = client.images(
            query=query,
            region=DDGS_REGION,
            safesearch='moderate',
            max_results=DDGS_MAX_RESULTS,
            backend=DDGS_BACKEND,
            type_image='photo',
        )
    return _select_images(list(results or []))


async def find_images(query: str) -> dict[str, str | None]:
    """Асинхронно найти картинки через синхронную библиотеку ``ddgs``.

    ``DDGS.images`` выполняет блокирующие сетевые запросы, поэтому весь поиск
    переносится через ``asyncio.to_thread`` и не блокирует event loop FastAPI.
    Ошибка или rate limit не отменяет создание события.
    """
    normalized_query = str(query).strip()
    if not normalized_query:
        return dict(_EMPTY_IMAGES)

    try:
        return await asyncio.to_thread(_find_images_sync, normalized_query)
    except Exception as error:
        logger.warning(
            'DDGS image search failed for %r; creating the event without images: %s',
            normalized_query,
            error,
        )
        return dict(_EMPTY_IMAGES)