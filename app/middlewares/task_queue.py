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
