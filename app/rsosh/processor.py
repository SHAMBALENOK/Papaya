"""RSOSH-импорт: оркестрация пайплайна.

``run_import(doc_id)`` — единственная async-функция всего конвейера:
preprocessing -> extraction -> parsing -> matching -> validation. Она вызывается
как из Celery-воркера (через отдельный процесс), так и напрямую в тестах.

HTTP-запрос НЕ ждёт пайплайн: POST /imports/rsosh только переводит документ в
PROCESSING и ставит задачу в очередь ``heavy``.
"""

import asyncio
import logging
import subprocess
import sys
from datetime import datetime, timezone

from app import database
from app.caching.main import cache_doc_outside_request
from app.middlewares.task_queue import task_queue
from app.rsosh import extraction, parsing, preprocessing, states, validation
from app.rsosh.states import docs_metadata_with_section, rsosh_section

logger = logging.getLogger('papaya.rsosh.processor')


async def _cache_doc(doc: dict) -> None:
    """Кэш-запись пайплайна: сбой Redis не должен валить импорт."""
    try:
        await cache_doc_outside_request(doc)
    except Exception:  # noqa: BLE001
        logger.warning('failed to update cached doc', exc_info=True)


async def _ensure_rsosh_doc(doc_id: str) -> dict:
    doc = await database.docs.get_doc(doc_id)
    if not doc:
        raise LookupError(f'Document {doc_id} not found')
    return doc


async def _set_processing(doc: dict) -> dict:
    section = {
        'state': states.STATE_PROCESSING,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'finished_at': None,
        'error': None,
        'summary': None,
        'candidates': [],
        'confirm': None,
    }
    updated = await database.docs.edit_doc(
        doc['id'],
        {
            'status': states.STATE_TO_DOC_STATUS[states.STATE_PROCESSING],
            'metadata': docs_metadata_with_section(doc, section),
        },
    )
    await _cache_doc(updated)
    return updated


async def _complete(doc: dict, section_suffix: dict) -> dict:
    """Записать результат пайплайна, выбрать status документа, вернуть секцию."""
    doc = await database.docs.get_doc(doc['id'])
    section = dict(rsosh_section(doc))
    section.update(section_suffix)
    state = section['state']
    updated = await database.docs.edit_doc(
        doc['id'],
        {
            'status': states.STATE_TO_DOC_STATUS[state],
            'metadata': docs_metadata_with_section(doc, section),
        },
    )
    await _cache_doc(updated)
    return rsosh_section(updated)


async def run_import(doc_id: str) -> dict:
    """Выполнить весь пайплайн импорта и вернуть итоговую секцию rsosh.

    Идемпотентность: повторный запуск возможен только из UPLOADED/FAILED
    (перевод в PROCESSING происходит из route; здесь проверяем только наличие).
    """
    doc = await _ensure_rsosh_doc(doc_id)
    if doc['status'] not in states.STARTABLE_DOC_STATUSES:
        raise ValueError(
            f'Import is not startable from status {doc["status"]}; '
            f'startable: {states.STARTABLE_DOC_STATUSES}'
        )

    doc = await _set_processing(doc)

    try:
        source_path = preprocessing.resolve_doc_file(doc)
        if not source_path:
            raise ValueError('Document has no local file copy')

        xlsx_path = await asyncio.to_thread(extraction.extract_xlsx, source_path)
        records = parsing.parse_xlsx(xlsx_path)
        candidates = await matching_impl(records, doc)
        candidates = validation.validate_candidates(candidates)

        summary = validation.summarize(candidates)
        # Preview всегда требует подтверждения админа, даже если всё распознано
        # уверенно: импорт без confirm ничего не пишет в БД.
        state = states.STATE_REVIEW

        return await _complete(
            doc,
            {
                'state': state,
                'finished_at': datetime.now(timezone.utc).isoformat(),
                'error': None,
                'summary': summary,
                'candidates': candidates,
            },
        )
    except Exception as exc:  # noqa: BLE001 — FAILED обязан отразить ошибку
        return await _complete(
            doc,
            {
                'state': states.STATE_FAILED,
                'finished_at': datetime.now(timezone.utc).isoformat(),
                'error': f'{type(exc).__name__}: {exc}',
            },
        )


async def matching_impl(records: list[dict], doc: dict) -> list[dict]:
    """Хук для тестов: сопоставление по нормализованному названию."""
    from app.rsosh import matching

    return await matching.match_records(records, doc)


@task_queue.task(
    queue='heavy',
    time_limit=None,
    soft_time_limit=None,
)
def rsosh_import_task(doc_id: str) -> None:
    """Celery-задача: импорт в отдельном процессе (свой event loop и движок).

    Как и подготовка тестовой БД (conftest), пайплайн выполняется в
    subprocess: модульный async-движок (AsyncSessionLocal) привязан к loop, и
    переиспользование его из разных потоков воркера ломает пул соединений.
    """
    subprocess.run(
        [sys.executable, '-m', 'app.rsosh.worker_run', str(doc_id)],
        check=False,
    )