"""Состояние прогона импорта РСОШ и его отчёт.

Отдельная таблица прогонов не нужна: прогон — это обработка конкретного
документа, поэтому всё состояние живёт в ``docs.metadata['rsosh']``.

    {
      "state": "processing|review|approved|rejected|failed",
      "started_at": "ISO-8601",
      "finished_at": "ISO-8601",
      "error": "str|null",
      "summary": {"total": n, "new": n, "merge": n, "review": n},
      "pages": [PageReport, ...],
      "warnings": ["строка", ...],
      "candidates": [Candidate, ...],
      "confirm": {
        "confirmed_at": "ISO-8601",
        "created": n, "updated": n, "archived": [str, ...],
        "skipped": [str, ...],
        "errors": [str, ...]
      }
    }

Поле ``docs.status`` отражает фазу обработки документа:
``UPLOADED`` → ``PROCESSING`` → ``PROCESSED`` / ``NEEDS_REVIEW`` / ``FAILED``
(либо ``REJECTED``, если администратор отклонил результаты).
"""

from datetime import datetime, timezone

DOCS_STATUS = {
    'processing': 'PROCESSING',
    'review': 'NEEDS_REVIEW',
    'approved': 'PROCESSED',
    'rejected': 'REJECTED',
    'failed': 'FAILED',
}

STARTABLE_STATES = ('processing', 'review', 'failed')
CONFIRMABLE_STATES = ('review',)
#: Отклонить можно только уже готовый к проверке прогон. ``processing`` сюда
#: не входит намеренно: пока идёт обработка, ``reject`` и воркер пишут в один
#: и тот же прогон, и гонка заканчивалась бы документом, отклонённым «поверх»
#: свежезаписанного результата (или результатом, перетёршим отклонение).
#: Отклонение работающего импорта — 409 из ``reject_confirmed_import``.
REJECTABLE_STATES = ('review',)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rsosh_section(doc: dict | None) -> dict:
    """Раздел ``rsosh`` метаданных документа (создаётся при первом обращении)."""
    metadata = (doc or {}).get('metadata') or {}
    section = metadata.get('rsosh')
    if not isinstance(section, dict):
        section = {}
    return section


def docs_metadata_with_section(doc: dict | None, section: dict) -> dict:
    """Метаданные документа с обновлённым разделом ``rsosh``."""
    metadata = dict((doc or {}).get('metadata') or {})
    metadata['rsosh'] = section
    return metadata


def start_section(doc: dict | None) -> dict:
    """Раздел в состоянии «идёт обработка» (ошибки прошлого прогона сброшены)."""
    previous = rsosh_section(doc)
    return {
        **previous,
        'state': 'processing',
        'started_at': _now(),
        'finished_at': None,
        'error': None,
        'candidates': [],
        'confirm': None,
    }


def review_section(
    doc: dict | None,
    *,
    candidates: list[dict],
    pages: list[dict],
    warnings: list[str],
    summary: dict,
) -> dict:
    """Раздел в состоянии «готов к подтверждению»."""
    return {
        **rsosh_section(doc),
        'state': 'review',
        'finished_at': _now(),
        'error': None,
        'summary': summary,
        'pages': pages,
        'warnings': warnings,
        'candidates': candidates,
    }


def failed_section(doc: dict | None, error: str) -> dict:
    """Раздел в состоянии «ошибка обработки» с сохранением причины."""
    return {
        **rsosh_section(doc),
        'state': 'failed',
        'finished_at': _now(),
        'error': error,
        'candidates': [],
    }


def confirmed_section(doc: dict | None, result: dict) -> dict:
    """Раздел в состоянии «импорт применён» с итогами записи."""
    return {
        **rsosh_section(doc),
        'state': 'approved',
        'finished_at': _now(),
        'confirm': result,
    }


def rejected_section(doc: dict | None) -> dict:
    """Раздел в состоянии «администратор отклонил результаты»."""
    return {
        **rsosh_section(doc),
        'state': 'rejected',
        'finished_at': _now(),
    }
