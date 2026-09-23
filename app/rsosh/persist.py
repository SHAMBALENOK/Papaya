"""RSOSH-импорт: подтверждение (persist) и отклонение кандидатов.

Persist выполняется ТОЛЬКО по явному confirm админа и в рамках единой
транзакции get/проверки/metadata. Кандидаты без подтверждения никогда не
создают записи в ``olympiads``/``organizations``.
"""

import logging
from datetime import datetime, timezone

from app import database
from app.caching.main import (
    cache_doc_after_write,
    get_standalone_redis,
    invalidate_olympiad,
)
from app.rsosh import states
from app.rsosh.states import docs_metadata_with_section, rsosh_section

logger = logging.getLogger('papaya.rsosh.persist')


async def _refresh_caches(doc: dict, candidates: list[dict]) -> None:
    """Обновить кэш карточки доки и пометить списки олимпиад устаревшими."""
    client = get_standalone_redis()
    try:
        await cache_doc_after_write(client, doc)
        for candidate in candidates:
            created_id = candidate.get('created_id')
            if created_id:
                await invalidate_olympiad(client, created_id)
    except Exception:  # noqa: BLE001 — сбой кэша не должен ломать персист
        logger.warning('failed to refresh caches after confirm', exc_info=True)
    finally:
        close = getattr(client, 'aclose', client.close)
        await close()


async def _ensure_confirmable(doc_id: str) -> dict:
    doc = await database.docs.get_doc(doc_id)
    if not doc:
        raise LookupError(f'Document {doc_id} not found')
    section = rsosh_section(doc)
    if section.get('state') not in states.REVIEWABLE:
        raise ValueError(
            f'Import state {section.get("state")} is not confirmable'
        )
    if not isinstance(section.get('candidates'), list):
        raise ValueError('Import has no parsed candidates')
    return doc


async def _persist_one(doc: dict, candidate: dict) -> dict:
    """Создать/объединить олимпиаду по кандидату (без общей транзакции)."""
    organizer_ids = (
        [doc['organization_id']]
        if doc.get('organization_id')
        else (candidate.get('organizer_ids') or [])
    )
    base = {
        'name': candidate['name'],
        'subjects': candidate.get('subjects') or [],
        'levels': candidate.get('levels') or [],
        'years': candidate.get('years') or [],
        'description': candidate.get('description'),
        'metadata': {'source_doc_id': str(doc['id']), 'rsosh': True},
    }

    if candidate['action'] == states.ACTION_MERGE:
        existing_id = candidate['matched_olympiad_id']
        if not existing_id:
            return {'candidate': candidate, 'error': 'missing matched olympiad'}
        existing = await database.olympiads.get_olympiad(existing_id)
        if not existing:
            candidate['action'] = states.ACTION_CREATE
        else:
            merged = {
                'subjects': sorted(
                    set(existing.get('subjects') or []) | set(base['subjects'])
                ),
                'levels': sorted(
                    set(existing.get('levels') or []) | set(base['levels'])
                ),
                'years': sorted(
                    set(existing.get('years') or []) | set(base['years'])
                ),
            }
            if not existing.get('description') and base['description']:
                merged['description'] = base['description']
            metadata = dict(existing.get('metadata') or {})
            metadata.setdefault('source_docs', []).append(str(doc['id']))
            merged['metadata'] = metadata
            updated = await database.olympiads.edit_olympiad(existing_id, merged)
            if not updated:
                return {'candidate': candidate, 'error': 'merge failed'}
            candidate['persisted'] = True
            candidate['created_id'] = updated['id']
            return {'candidate': candidate}

    created = await database.olympiads.add_olympiad(
        {
            **base,
            'organizer_ids': organizer_ids,
            'status': 'PUBLISHED',
        }
    )
    candidate['persisted'] = True
    candidate['created_id'] = created['id']
    return {'candidate': candidate}


async def confirm_import(doc_id: str) -> dict:
    """Применить импорт: создать/объединить олимпиады, пометить APPROVED."""
    doc = await _ensure_confirmable(doc_id)
    section = dict(rsosh_section(doc))
    candidates = list(section.get('candidates') or [])
    confirmed = []
    for candidate in candidates:
        if candidate.get('persisted'):
            confirmed.append({'candidate': candidate, 'skipped': True})
            continue
        result = await _persist_one(doc, candidate)
        if result.get('error'):
            confirmed.append(
                {
                    'candidate': result['candidate'],
                    'error': result['error'],
                    'skipped': True,
                }
            )
        else:
            confirmed.append({'candidate': result['candidate']})

    section['candidates'] = candidates
    section['state'] = states.STATE_APPROVED
    section['finished_at'] = datetime.now(timezone.utc).isoformat()
    section['confirm'] = {
        'confirmed_at': datetime.now(timezone.utc).isoformat(),
        'results': confirmed,
    }
    updated = await database.docs.edit_doc(
        doc_id,
        {
            'status': states.STATE_TO_DOC_STATUS[states.STATE_APPROVED],
            'metadata': docs_metadata_with_section(doc, section),
        },
    )
    await _refresh_caches(updated, candidates)
    return updated


async def reject_import(doc_id: str) -> dict:
    """Отклонить импорт: ничего не пишем, состояние — rejected (status NEEDS_REVIEW)."""
    doc = await _ensure_confirmable(doc_id)
    section = dict(rsosh_section(doc))
    section['state'] = states.STATE_REJECTED
    section['finished_at'] = datetime.now(timezone.utc).isoformat()
    section['rejected_at'] = datetime.now(timezone.utc).isoformat()
    updated = await database.docs.edit_doc(
        doc_id,
        {
            'status': states.STATE_TO_DOC_STATUS[states.STATE_REJECTED],
            'metadata': docs_metadata_with_section(doc, section),
        },
    )
    await _refresh_caches(updated, section.get('candidates') or [])
    return updated