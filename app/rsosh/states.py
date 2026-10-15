"""Состояние прогона импорта РСОШ и его отчёт.

Отдельная таблица прогонов не нужна: прогон — это обработка конкретного
документа, поэтому всё состояние живёт в ``docs.metadata['rsosh']``.

    {
      "state": "processing|paused|review|approved|rejected|failed",
      "started_at": "ISO-8601",
      "finished_at": "ISO-8601",
      "error": "str|null",
      "progress": {"stage": "starting|extracting|matching|done", ...},
      "pause_requested": bool,
      "summary": {"total": n, "new": n, "merge": n, "review": n},
      "pages": [PageReport, ...],
      "warnings": ["строка", ...],
      "candidates": [Candidate, ...],
      "selection": {"skip": [...], "rename": {...}, "descriptions": {...},
                    "merge": {...}, "archive_missing": bool},
      "confirm": {
        "confirmed_at": "ISO-8601",
        "created": n, "updated": n, "archived": [str, ...],
        "skipped": [str, ...],
        "errors": [str, ...]
      }
    }

Поле ``progress`` хранит этап обработки, чтобы панель показывала ход импорта,
а не только «processing». Поле ``records`` появляется только в состоянии
``paused``: это контрольная точка (уже распознанные строки), из которой
``resume`` продолжает обработку без повторного чтения документа.

Поле ``docs.status`` отражает фазу обработки документа:
``UPLOADED`` → ``PROCESSING`` → ``PROCESSED`` / ``NEEDS_REVIEW`` / ``FAILED``
(либо ``PAUSED``, если обработку приостановили, либо ``REJECTED``, если
администратор отклонил результаты).
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
#: Отклонить можно уже готовый к проверке прогон и приостановленный импорт
#: (администратор вправе отказаться от приостановленного прогона). ``processing``
#: сюда не входит намеренно: пока идёт обработка, ``reject`` и воркер пишут в
#: один и тот же прогон, и гонка заканчивалась бы документом, отклонённым
#: «поверх» свежезаписанного результата (или результатом, перетёршим
#: отклонение). Отклонение работающего импорта — 409 из
#: ``reject_confirmed_import``.
REJECTABLE_STATES = ('review', 'paused')


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
    """Раздел в состоянии «идёт обработка» (ошибки прошлого прогона сброшены).

    Новый прогон начинается с чистого листа: выбор администратора и
    контрольная точка приостановки относятся к прежним кандидатам и не должны
    пережить перезапуск.
    """
    previous = rsosh_section(doc)
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
    """Раздел с обновлённым этапом обработки, остающийся в ``processing``.

    Запись этапа — это не смена состояния прогона: документ продолжает
    обрабатываться. Функция нужна, чтобы панель показывала ход импорта, а
    ``GET /imports/{id}`` отвечал на понятный вопрос «что сейчас происходит»,
    а не только «processing».
    """
    section = {**rsosh_section(doc), 'state': 'processing'}
    section['progress'] = {'stage': stage, **extra}
    return section


def paused_section(
    doc: dict | None,
    *,
    stage: str,
    records: list[dict] | None = None,
    pages: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Раздел в состоянии «обработка приостановлена».

    ``records`` — контрольная точка: если приостановка случилась после
    распознавания документа, уже готовые строки сохраняются, и ``resume``
    продолжает обработку с сопоставления, не читая документ заново. Для
    приостановки до распознавания точка пуста, и возобновление начинает
    обработку с начала.
    """
    section = {**rsosh_section(doc), 'state': 'paused', 'pause_requested': False}
    section['progress'] = {'stage': stage}
    if records is not None:
        section['records'] = records
    if pages is not None:
        section['pages'] = pages
    if warnings is not None:
        section['warnings'] = warnings
    return section


def resumed_section(doc: dict | None) -> dict:
    """Раздел, возвращающий приостановленный прогон в ``processing``.

    Контрольная точка (``records``) и распознанные страницы намеренно
    сохраняются: их использует ``processor.resume_import``.
    """
    section = {**rsosh_section(doc), 'state': 'processing'}
    section['pause_requested'] = False
    section['progress'] = {'stage': 'resuming'}
    return section


def selection_section(doc: dict | None, selection: dict) -> dict:
    """Раздел с сохранённым выбором администратора.

    Выбор (кого подтвердить, кого снять, какие правки названия/описания/
    объединения сделаны) хранится вместе с прогоном, поэтому переживает
    перезагрузку страницы и переход между устройствами.
    """
    return {**rsosh_section(doc), 'selection': selection}


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
        'progress': {'stage': 'done'},
        'pause_requested': False,
        # Кандидаты и страницы уже сохранены; сырые строки-источник больше не
        # нужны и не должны оставаться в метаданных готового прогона.
        'records': None,
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
        'progress': {'stage': 'failed'},
        'pause_requested': False,
        'records': None,
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
