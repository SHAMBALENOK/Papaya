import asyncio
import os

from celery import Celery


REDIS_URL = os.getenv('REDIS_URL')
if not REDIS_URL:
    host = os.getenv('REDIS_HOST', 'localhost')
    port = os.getenv('REDIS_PORT', '6379')
    REDIS_URL = f'redis://{host}:{port}/0'


task_queue = Celery(
    'main',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

task_queue.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    # Время обработки пользовательского PDF зависит от его размера. На уровне
    # Celery нет ни hard-, ни soft-limit; HTTP-маршрут также ждёт без timeout.
    task_time_limit=None,
    task_soft_time_limit=None,
    imports=(
        'app.middlewares.parse_tables.pdf_processing',
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