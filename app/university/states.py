"""Состояние прогона импорта приказа университета и его отчёт.

Отдельная таблица прогонов не нужна: прогон — это обработка конкретного
документа, поэтому всё состояние живёт в ``docs.metadata['university']``.
Раздел отдельный от ``rsosh``: один и тот же документ не может быть
одновременно перечнем РСОШ и приказом вуза, а раздельные ключи делают
состояния независимыми и не мешают друг другу.

    {
      "state": "processing|paused|review|approved|rejected|failed",
      "started_at": "ISO-8601",
      "finished_at": "ISO-8601",
      "error": "str|null",
      "progress": {"stage": "starting|extracting|matching|done", ...},
      "pause_requested": bool,
      "summary": {"total": n, "linked": n, "review": n, "unmatched": n},
      "university": {"name": "...", "name_norm": "...", "matched_id": "...|null",
                     "matched_name": "...|null", "match_score": 0.0},
      "pages": [PageReport, ...],
      "warnings": ["строка", ...],
      "candidates": [UniversityCandidate, ...],
      "selection": {"skip": [...], "links": {name_norm: olympiad_id},
                    "university_id": "...|null"},
      "confirm": {
        "confirmed_at": "ISO-8601",
        "linked": n, "updated": n, "skipped": [str, ...],
        "errors": [str, ...]
      }
    }

Поле ``progress`` хранит этап обработки, чтобы панель показывала ход импорта,
а не только «processing». Поле ``records`` появляется только в состоянии
``paused``: это контрольная точка, из которой ``resume`` продолжает обработку
без повторного чтения документа.

Поле ``docs.status`` отражает фазу обработки документа — те же значения, что и
у РСОШ: ``UPLOADED`` → ``PROCESSING`` → ``PROCESSED`` / ``NEEDS_REVIEW`` /
``FAILED`` (либо ``PAUSED``, либо ``REJECTED``).
"""

from datetime import datetime, timezone

DOCS_STATUS = {
    'processing': 'PROCESSING',
    'paused': 'PAUSED',
    'review': 'NEEDS_REVIEW',
    'approved': 'PROCESSED',
    'rejected': 'REJECTED',
    'failed': 'FAILED',
}

STARTABLE_STATES = ('processing', 'review', 'failed')
CONFIRMABLE_STATES = ('review',)
REJECTABLE_STATES = ('review', 'paused')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def university_section(doc: dict | None) -> dict:
    """Раздел ``university`` метаданных документа (создаётся при обращении)."""
    metadata = (doc or {}).get('metadata') or {}
    section = metadata.get('university')
    if not isinstance(section, dict):
        section = {}
    return section


def docs_metadata_with_section(doc: dict | None, section: dict) -> dict:
    """Метаданные документа с обновлённым разделом ``university``."""
    metadata = dict((doc or {}).get('metadata') or {})
    metadata['university'] = section
    return metadata


def start_section(doc: dict | None) -> dict:
    """Раздел в состоянии «идёт обработка» (результат прошлого прогона сброшен)."""
    previous = university_section(doc)
    return {
        **previous,
        'state': 'processing',
        'started_at': _now(),
        'finished_at': None,
        'error': None,
        'candidates': [],
        'confirm': None,
        'progress': {'stage': 'starting'},
        'pause_requested': False,
        'records': None,
        'selection': None,
    }


def progress_section(doc: dict | None, *, stage: str, **extra) -> dict:
    """Раздел с обновлённым этапом обработки, остающийся в ``processing``."""
    section = {**university_section(doc), 'state': 'processing'}
    section['progress'] = {'stage': stage, **extra}
    return section


def paused_section(
    doc: dict | None,
    *,
    stage: str,
    records: list[dict] | None = None,
    pages: list[dict] | None = None,
    warnings: list[str] | None = None,
    university: dict | None = None,
) -> dict:
    """Раздел в состоянии «обработка приостановлена».

    ``records`` — контрольная точка: уже распознанные строки сохраняются, и
    ``resume`` продолжает с сопоставления, не читая документ заново.
    """
    section = {**university_section(doc), 'state': 'paused', 'pause_requested': False}
    section['progress'] = {'stage': stage}
    if records is not None:
        section['records'] = records
    if pages is not None:
        section['pages'] = pages
    if warnings is not None:
        section['warnings'] = warnings
    if university is not None:
        section['university'] = university
    return section


def resumed_section(doc: dict | None) -> dict:
    """Раздел, возвращающий приостановленный прогон в ``processing``."""
    section = {**university_section(doc), 'state': 'processing'}
    section['pause_requested'] = False
    section['progress'] = {'stage': 'resuming'}
    return section


def selection_section(doc: dict | None, selection: dict) -> dict:
    """Раздел с сохранённым выбором администратора."""
    return {**university_section(doc), 'selection': selection}


def review_section(
    doc: dict | None,
    *,
    candidates: list[dict],
    pages: list[dict],
    warnings: list[str],
    summary: dict,
    university: dict,
) -> dict:
    """Раздел в состоянии «готов к подтверждению»."""
    return {
        **university_section(doc),
        'state': 'review',
        'finished_at': _now(),
        'error': None,
        'progress': {'stage': 'done'},
        'pause_requested': False,
        'records': None,
        'summary': summary,
        'university': university,
        'pages': pages,
        'warnings': warnings,
        'candidates': candidates,
    }


def failed_section(doc: dict | None, error: str) -> dict:
    """Раздел в состоянии «ошибка обработки» с сохранением причины."""
    return {
        **university_section(doc),
        'state': 'failed',
        'finished_at': _now(),
        'error': error,
        'progress': {'stage': 'failed'},
        'pause_requested': False,
        'records': None,
        'candidates': [],
    }


def confirmed_section(doc: dict | None, result: dict) -> dict:
    """Раздел в состоянии «импорт применён» с итогами записи."""
    return {
        **university_section(doc),
        'state': 'approved',
        'finished_at': _now(),
        'confirm': result,
    }


def rejected_section(doc: dict | None) -> dict:
    """Раздел в состоянии «администратор отклонил результаты»."""
    return {
        **university_section(doc),
        'state': 'rejected',
        'finished_at': _now(),
    }
