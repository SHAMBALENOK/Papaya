import asyncio

from celery import Celery

from app.core.config import REDIS_URL


task_queue = Celery(
    'main',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

task_queue.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    # Время обработки документа РСОШ зависит от количества страниц и от того,
    # потребуется ли OCR. На уровне Celery нет ни hard-, ни soft-limit.
    task_time_limit=None,
    task_soft_time_limit=None,
    imports=(
        'app.rsosh.worker',
    ),
)


async def run_task(task, *args, **kwargs):
    """Запустить задачу без лимитов и дождаться результата вне worker task."""
    result = task.apply_async(
        args=args,
        kwargs=kwargs,
        time_limit=None,
        soft_time_limit=None,
    )
    return await asyncio.to_thread(
        result.get,
        timeout=None,
        disable_sync_subtasks=True,
    )