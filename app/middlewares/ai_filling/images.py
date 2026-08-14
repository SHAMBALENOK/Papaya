from app.middlewares.task_queue import task_queue, AsyncCeleryTask
from asyncddgs import aDDGS
from fastapi import HTTPException

@task_queue.task(base=AsyncCeleryTask, time_limit=2, default_retry_delay=1, retry_backoff=True, retry_backoff_max=3, queue="medium")
async def find_images(query: str) -> dict[str, str]:
    """
    Function to search for preview picture and background picture
    """
    try:
        async with aDDGS() as ddgs:
            preview_picture = await ddgs.images(
                keywords=query,
                region="ru-ru",
                max_results=1,
                size="Medium",
                layout="Square",
            )
            preview_picture = preview_picture[0].get("url")

            picture = await ddgs.images(
                keywords=query,
                region="ru-ru",
                max_results=1,
                size="Large",
                layout="Wide"
            )
            picture = picture[0].get("url")

        return {
            "preview_picture": preview_picture,
            "picture": picture,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error: \n{e}\n in images engine")