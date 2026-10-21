"""Celery-задача импорта приказа университета.

Celery-воркер работает в синхронном контексте и не имеет запущенного event
loop, а ``run_import`` использует async SQLAlchemy. Поэтому задача не делает
ничего, кроме запуска подпроцесса с тем же модулем: свежий интерпретатор со
своим loop (иначе второй ``asyncio.run`` в том же процессе был бы ошибкой).

    python -m app.university.worker_run <doc_id>

Результат пишется в состояние документа, поэтому HTTP-слой читает прогресс
обычным запросом и не ждёт завершения задачи.

Если подпроцесс сам не смог выполнить обработку — не запустился или упал до
записи результата — задача помечает документ ``failed``: документ уже
переведён в ``PROCESSING`` при старте, и без отметки он завис бы в этом
состоянии навсегда.
"""

import asyncio
import logging
import subprocess
import sys

from app.middlewares.task_queue import task_queue

logger = logging.getLogger('papaya.university.worker')

WORKER_MODULE = 'app.university.worker_run'

#: Текст ошибки документа, когда процесс обработки завершился неуспешно.
CRASHED_IMPORT_ERROR = (
    'Обработка неожиданно завершилась: процесс остановился до записи '
    'результата. Запустите импорт заново.'
)


def _mark_crashed_import_failed(doc_id) -> None:
    """Перевести зависший импорт в ``failed`` после падения подпроцесса.

    Импорт ``persist`` отложенный: задача-обёртка должна оставаться лёгкой, а
    ``asyncio.run`` здесь безопасен — Celery-задача синхронна и собственного
    event loop в ней нет.

    Ошибка отметки не поднимается: основная причина — падение подпроцесса.
    """
    from app.university import persist

    try:
        asyncio.run(
            persist.mark_import_failed_if_stuck(doc_id, error=CRASHED_IMPORT_ERROR)
        )
    except Exception:  # noqa: BLE001 - не маскировать исходную ошибку импорта
        logger.exception(
            'university: failed to mark crashed import %s as failed', doc_id
        )


@task_queue.task(
    name='papaya.university.import',
    time_limit=None,
    soft_time_limit=None,
    queue='heavy',
)
def university_import_task(doc_id: str) -> None:
    """Обработать документ приказа университета в отдельном процессе."""
    command = [sys.executable, '-m', WORKER_MODULE, str(doc_id)]
    logger.info('university: starting import worker for document %s', doc_id)
    try:
        result = subprocess.run(command, check=False)
    except OSError:
        # Подпроцесс не удалось даже запустить: документ уже в PROCESSING
        # (claim до постановки задачи) и завис бы без отметки failed.
        logger.exception('university: failed to start import worker for %s', doc_id)
        _mark_crashed_import_failed(doc_id)
        raise
    if result.returncode != 0:
        # worker_run.main возвращает 0 только когда состояние review, и 1 —
        # когда состояние уже записано (failed и т.п.). Ненулевой код здесь
        # означает, что процесс упал до записи результата:
        # mark_import_failed_if_stuck сам разберётся, застрял ли документ, и
        # чужой результат не тронет.
        logger.warning(
            'university: import worker for %s exited with code %s',
            doc_id,
            result.returncode,
        )
        _mark_crashed_import_failed(doc_id)
