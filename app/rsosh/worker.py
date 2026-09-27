"""Celery-задача импорта РСОШ.

Celery-воркер работает в синхронном контексте и не имеет запущенного event
loop, а ``run_import`` использует async SQLAlchemy. Поэтому задача не делает
ничего, кроме запуска подпроцесса с тем же модулем: свежий интерпретатор со
своим loop (иначе второй ``asyncio.run`` в том же процессе был бы ошибкой).

    python -m app.rsosh.worker_run <doc_id>

Результат пишется в состояние документа, поэтому HTTP-слой читает прогресс
обычным запросом и не ждёт завершения задачи.
"""

import logging
import subprocess
import sys

from app.middlewares.task_queue import task_queue

logger = logging.getLogger('papaya.rsosh.worker')

WORKER_MODULE = 'app.rsosh.worker_run'


@task_queue.task(
    name='papaya.rsosh.import',
    time_limit=None,
    soft_time_limit=None,
    queue='heavy',
)
def rsosh_import_task(doc_id: str) -> None:
    """Обработать документ РСОШ в отдельном процессе."""
    command = [sys.executable, '-m', WORKER_MODULE, str(doc_id)]
    logger.info('rsosh: starting import worker for document %s', doc_id)
    subprocess.run(command, check=False)
