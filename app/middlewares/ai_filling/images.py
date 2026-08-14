import logging
from app.middlewares.task_queue import task_queue, AsyncCeleryTask
from asyncddgs import aDDGS

logger = logging.getLogger(__name__)


def _first_image_url(results) -> str | None:
    """
    Достаёт URL первой картинки из ответа DuckDuckGo.

    Разные версии asyncddgs/ddgs могут возвращать разные структуры;
    любые неожиданности здесь сводятся к None вместо краха задачи.
    """
    if isinstance(results, (list, tuple)) and results:
        first = results[0]
        if isinstance(first, dict):
            return first.get("url")
    return None


@task_queue.task(base=AsyncCeleryTask, time_limit=60, default_retry_delay=1, retry_backoff=True, retry_backoff_max=3, queue="medium")
async def find_images(query: str) -> dict[str, str | None]:
    """
    Ищет картинку-превью и фоновую картинку для события.

    Ошибки поиска не фатальны: возвращаем None вместо картинок,
    событие всё равно будет создано.
    """
    preview_picture: str | None = None
    picture: str | None = None
    try:
        async with aDDGS() as ddgs:
            preview = await ddgs.images(
                keywords=query,
                region="ru-ru",
                max_results=1,
                size="Medium",
                layout="Square",
            )
            large = await ddgs.images(
                keywords=query,
                region="ru-ru",
                max_results=1,
                size="Large",
                layout="Wide",
            )
        preview_picture = _first_image_url(preview)
        picture = _first_image_url(large)
    except Exception as e:
        logger.warning("Image search failed for %r: %s", query, e)

    return {
        "preview_picture": preview_picture,
        "picture": picture,
    }
