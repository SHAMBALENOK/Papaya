"""REST-эндпоинты RSOSH-импорта.

POST /api/v1/imports/rsosh    — начать импорт (async: ставит Celery-задачу)
GET  /api/v1/imports/{id}     — статус импорта
GET  /api/v1/imports/{id}/preview — кандидаты для подтверждения
POST /api/v1/imports/{id}/confirm — применить импорт (создать олимпиады)
POST /api/v1/imports/{id}/reject  — отклонить импорт (ничего не пишет)

Создание/объединение олимпиад происходит только по явному confirm.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import database
from app.caching.main import (
    cache_doc_after_write,
    get_cached_doc,
    get_redis,
)
from app.core.cache_guard import safe_cache_write
from app.core.deps import require_org_admin_or_admin
from app.rsosh import states
from app.rsosh.persist import confirm_import, reject_import
from app.rsosh.processor import rsosh_import_task
from app.rsosh.states import docs_metadata_with_section, rsosh_section


imports_page = APIRouter(
    prefix='/imports',
    tags=['imports'],
)

logger = logging.getLogger('papaya.imports')


class RsoshStartRequest(BaseModel):
    doc_id: UUID


def _can_manage_doc(current_user: dict, doc: dict) -> bool:
    if current_user.get('role') == 'ADMIN':
        return True
    org_id = doc.get('organization_id')
    if not org_id:
        return False
    return current_user.get('organization_id') == org_id


@imports_page.post(
    '/rsosh',
    responses={
        202: {'description': 'Import started (processing in background)'},
        400: {'description': 'Invalid document type or status'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Document not found'},
        500: {'description': 'Internal server error'},
    },
)
async def start_rsosh_import(
    payload: RsoshStartRequest,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        doc = await get_cached_doc(
            r,
            str(payload.doc_id),
            lambda: database.docs.get_doc(str(payload.doc_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        if doc.get('type') != 'RSOSH_LIST':
            raise HTTPException(
                status_code=400,
                detail='Only RSOSH_LIST documents can be imported',
            )
        if doc.get('status') not in states.STARTABLE_DOC_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f'Import not startable from status {doc.get("status")}',
            )

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
            str(payload.doc_id),
            {
                'status': states.STATE_TO_DOC_STATUS[states.STATE_PROCESSING],
                'metadata': docs_metadata_with_section(doc, section),
            },
        )
        await safe_cache_write(cache_doc_after_write(r, updated))

        try:
            rsosh_import_task.delay(str(payload.doc_id))
        except Exception:
            logger.exception('Failed to enqueue rsosh import; reverting')
            await database.docs.edit_doc(
                str(payload.doc_id),
                {
                    'status': doc.get('status') or 'UPLOADED',
                    'metadata': dict(doc.get('metadata') or {}),
                },
            )
            raise HTTPException(
                status_code=503,
                detail='Import queue is unavailable',
            )

        return JSONResponse(
            status_code=202,
            content={
                'import_id': str(payload.doc_id),
                'status': states.STATE_PROCESSING,
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '',
    responses={
        200: {'description': 'List of RSOSH imports'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        500: {'description': 'Internal server error'},
    },
)
async def list_imports(
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    """Список импортов: админ видит все, орг-админ — только своей организации."""
    try:
        organization_id = None
        if current_user.get('role') != 'ADMIN':
            organization_id = current_user.get('organization_id')

        docs = await database.docs.list_docs(
            doc_type='RSOSH_LIST',
            organization_id=organization_id,
        )
        items = []
        for doc in docs:
            section = rsosh_section(doc)
            if not section.get('state'):
                continue
            summary = section.get('summary') or {}
            items.append({
                'import_id': str(doc['id']),
                'doc_name': doc.get('name'),
                'doc_status': doc.get('status'),
                'organization_id': doc.get('organization_id'),
                'state': section.get('state'),
                'started_at': section.get('started_at'),
                'finished_at': section.get('finished_at'),
                'error': section.get('error'),
                'summary': {
                    'total': summary.get('total') or 0,
                    'new': summary.get('new') or 0,
                    'merge': summary.get('merge') or 0,
                    'duplicate': summary.get('duplicate') or 0,
                    'review': summary.get('review') or 0,
                },
            })
        items.sort(
            key=lambda item: item.get('finished_at') or item.get('started_at') or '',
            reverse=True,
        )
        return items[:limit]
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/{import_id}',
    responses={
        200: {'description': 'Import status'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Import not found'},
        500: {'description': 'Internal server error'},
    },
)
async def import_status(
    import_id: UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        doc = await get_cached_doc(
            r,
            str(import_id),
            lambda: database.docs.get_doc(str(import_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Import not found')
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        section = rsosh_section(doc)
        return {
            'import_id': str(import_id),
            'status': section.get('state'),
            'doc_status': doc.get('status'),
            'error': section.get('error'),
            'summary': section.get('summary'),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/{import_id}/preview',
    responses={
        200: {'description': 'Import preview (candidates for confirmation)'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is still processing'},
        500: {'description': 'Internal server error'},
    },
)
async def import_preview(
    import_id: UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        doc = await get_cached_doc(
            r,
            str(import_id),
            lambda: database.docs.get_doc(str(import_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Import not found')
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        section = rsosh_section(doc)
        if section.get('state') == states.STATE_PROCESSING:
            raise HTTPException(
                status_code=409,
                detail='Import is still processing',
            )
        return {
            'import_id': str(import_id),
            'state': section.get('state'),
            'summary': section.get('summary'),
            'candidates': section.get('candidates') or [],
            'reviews': {
                candidate['name_norm']: candidate['reviews']
                for candidate in (section.get('candidates') or [])
                if candidate.get('reviews')
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/confirm',
    responses={
        200: {'description': 'Import confirmed and applied'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import not confirmable in its state'},
        500: {'description': 'Internal server error'},
    },
)
async def confirm(
    import_id: UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        doc = await get_cached_doc(
            r,
            str(import_id),
            lambda: database.docs.get_doc(str(import_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Import not found')
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        section = rsosh_section(doc)
        if section.get('state') not in states.REVIEWABLE:
            raise HTTPException(
                status_code=409,
                detail=f'Import state {section.get("state")} is not confirmable',
            )
        updated = await confirm_import(str(import_id))
        await safe_cache_write(cache_doc_after_write(r, updated))
        rsosh_section_updated = rsosh_section(updated)
        return JSONResponse(
            status_code=200,
            content={
                'import_id': str(import_id),
                'status': rsosh_section_updated.get('state'),
                'summary': rsosh_section_updated.get('summary'),
                'confirm': rsosh_section_updated.get('confirm'),
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/reject',
    responses={
        200: {'description': 'Import rejected (nothing persisted)'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import not confirmable in its state'},
        500: {'description': 'Internal server error'},
    },
)
async def reject(
    import_id: UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        doc = await get_cached_doc(
            r,
            str(import_id),
            lambda: database.docs.get_doc(str(import_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Import not found')
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        section = rsosh_section(doc)
        if section.get('state') not in states.REVIEWABLE:
            raise HTTPException(
                status_code=409,
                detail=f'Import state {section.get("state")} is not rejectable',
            )
        updated = await reject_import(str(import_id))
        await safe_cache_write(cache_doc_after_write(r, updated))
        return JSONResponse(
            status_code=200,
            content={
                'import_id': str(import_id),
                'status': states.STATE_REJECTED,
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')