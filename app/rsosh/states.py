"""RSOSH-импорт: состояния и стабильный keyspace в ``docs.metadata``.

Состояние импорта хранится прямо на документе (``Docs``), без отдельной
таблицы ``rsosh_imports`` — табл. «срочных» сущностей импорта здесь нет,
а вся промежуточная информация переживает рестарт/перезапуск без потерь.

Схема ``docs.metadata['rsosh']``::

    {
      "state": "processing|review|approved|rejected|failed",
      "started_at": "ISO",
      "finished_at": "ISO",
      "error": "str|null",
      "summary": {"total": n, "new": n, "merge": n, "duplicate": n, "review": n},
      "candidates": [ Candidate, ... ],
      "confirm": {
        "confirmed_at": "ISO",
        "results": [ {"candidate": Candidate, "error"?: str, "skipped"?: bool}, ... ]
      }
    }

Candidate (JSON в candidates)::

    {
      "name": str, "name_norm": str,
      "subjects": [str], "levels": [str], "years": [str],
      "description": str,
      "action": "create" | "merge" | "skip",
      "matched_olympiad_id": str|null,
      "confidence": "ok" | "review",
      "reviews": [str],
      "persisted": bool
    }

Статус документа (``Docs.status``) при этом отражает техническое состояние
обработки: UPLOADED -> PROCESSING -> PROCESSED / FAILED, а NEEDS_REVIEW
означает «есть что смотреть в preview и подтверждать/отклонять».
"""

RSOSH_METADATA_KEY = 'rsosh'

STATE_PROCESSING = 'processing'
STATE_REVIEW = 'review'
STATE_APPROVED = 'approved'
STATE_REJECTED = 'rejected'
STATE_FAILED = 'failed'

# Переносит документ в NEEDS_REVIEW, если состояние требует внимания админа.
STATE_TO_DOC_STATUS = {
    STATE_PROCESSING: 'PROCESSING',
    STATE_REVIEW: 'NEEDS_REVIEW',
    STATE_APPROVED: 'PROCESSED',
    STATE_REJECTED: 'NEEDS_REVIEW',
    STATE_FAILED: 'FAILED',
}

# Действия, в которые попадает («проигрывается») кандидат при подтверждении.
ACTION_CREATE = 'create'
ACTION_MERGE = 'merge'
ACTION_SKIP = 'skip'
ACTION_VALUES = (ACTION_CREATE, ACTION_MERGE, ACTION_SKIP)

# Начальные состояния, при которых импорт можно запустить/перезапустить.
STARTABLE_DOC_STATUSES = ('UPLOADED', 'FAILED')
# Состояния, при которых можно подтверждать/отклонять импорт.
REVIEWABLE = {STATE_REVIEW, STATE_APPROVED, STATE_REJECTED}


def rsosh_section(doc: dict) -> dict:
    """Вернуть (гарантированно словарь) секцию rsosh из метаданных документа."""
    metadata = doc.get('metadata') or {}
    section = metadata.get(RSOSH_METADATA_KEY)
    return section if isinstance(section, dict) else {}


def rsosh_state(doc: dict) -> str | None:
    return rsosh_section(doc).get('state')


def docs_metadata_with_section(doc: dict, section: dict) -> dict:
    """Новые метаданные документа, где 'rsosh' заменена переданной секцией."""
    metadata = dict(doc.get('metadata') or {})
    metadata[RSOSH_METADATA_KEY] = section
    return metadata