"""Запросы представителей на отсутствующие олимпиады, сезоны и профили.

Представитель не создаёт сущности каталога напрямую — он описывает, чего не
хватает. Администратор видит очередь, проверяет дубли и создаёт сущность
одобрением запроса. Это одновременно и модерация, и защита каталога от
дублей: одна олимпиада может быть заведена разными вузами под разными
названиями.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import database
from app.core import deps
from app.models.entity_requests import ENTITY_TYPES, REQUEST_STATUSES

university_requests_page = APIRouter(tags=['entity-requests'])
admin_requests_page = APIRouter(prefix='/admin/entity-requests', tags=['entity-requests'])

logger = logging.getLogger('papaya.entity_requests')

#: Какие поля будущей сущности можно передать в запросе. Остальное
#: отбрасывается: запрос — описание, а не способ записать произвольные данные.
_ALLOWED_PAYLOAD = {
    'OLYMPIAD': {'official_url', 'organizer'},
    'SEASON': set(),
    'PROFILE': {'rsosh_level'},
}


class EntityRequestCreate(BaseModel):
    entity_type: str = Field(description='OLYMPIAD | SEASON | PROFILE')
    name: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    payload: dict | None = None


class EntityRequestReject(BaseModel):
    reason: str


def _clean_payload(entity_type: str, payload: dict | None) -> dict:
    allowed = _ALLOWED_PAYLOAD.get(entity_type, set())
    return {k: v for k, v in (payload or {}).items() if k in allowed}


async def _validate_parent(entity_type: str, parent_id):
    if entity_type == 'OLYMPIAD':
        return None
    if entity_type == 'SEASON':
        parent = await database.olympiads.get_olympiad(parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        return parent_id
    season = await database.seasons.get_season(parent_id)
    if not season:
        raise HTTPException(status_code=404, detail='Season not found')
    return parent_id


@university_requests_page.get(
    '/universities/{university_id}/entity-requests'
)
async def list_university_requests(
    university_id: uuid.UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(deps.require_manage_university),
):
    """Запросы своего вуза: представитель видит только их."""
    try:
        if status is not None and status not in REQUEST_STATUSES:
            raise HTTPException(status_code=400, detail='Unknown status')
        requests, total = await database.entity_requests.list_requests(
            university_id=university_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            'requests': requests,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_requests_page.post(
    '/universities/{university_id}/entity-requests',
    status_code=201,
)
async def create_university_request(
    university_id: uuid.UUID,
    body: EntityRequestCreate,
    current_user: dict = Depends(deps.require_manage_university),
):
    """Попросить администратора добавить отсутствующую сущность."""
    try:
        entity_type = (body.entity_type or '').strip().upper()
        if entity_type not in ENTITY_TYPES:
            raise HTTPException(status_code=400, detail='Unknown entity type')
        name = (body.name or '').strip()
        if not name:
            raise HTTPException(status_code=400, detail='Name is required')
        if entity_type != 'OLYMPIAD' and body.parent_id is None:
            raise HTTPException(
                status_code=400,
                detail='Parent entity is required for season and profile',
            )
        parent_id = await _validate_parent(entity_type, body.parent_id)
        request = await database.entity_requests.create_request(
            {
                'entity_type': entity_type,
                'name': name,
                'description': body.description,
                'payload': _clean_payload(entity_type, body.payload),
                'university_id': str(university_id),
                'parent_id': str(parent_id) if parent_id else None,
            },
            user_id=current_user['id'],
        )
        await database.audit.log_action(
            'entity_request', request['id'], 'create',
            user_id=current_user['id'], after=request,
        )
        return request
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_requests_page.get('')
async def list_all_requests(
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    """Очередь запросов: серверные фильтры и честный ``total``."""
    try:
        if status is not None and status not in REQUEST_STATUSES:
            raise HTTPException(status_code=400, detail='Unknown status')
        if entity_type is not None and entity_type not in ENTITY_TYPES:
            raise HTTPException(status_code=400, detail='Unknown entity type')
        requests, total = await database.entity_requests.list_requests(
            status=status,
            entity_type=entity_type,
            search=search,
            limit=limit,
            offset=offset,
        )
        return {
            'requests': requests,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_requests_page.get('/{request_id}')
async def get_request(
    request_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    try:
        request = await database.entity_requests.get_request(request_id)
        if not request:
            raise HTTPException(status_code=404, detail='Request not found')
        return request
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_requests_page.post('/{request_id}/approve')
async def approve_request(
    request_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Создать сущность по запросу. Дубль — 409, запрос остаётся в очереди."""
    try:
        result = await database.entity_requests.approve_request(
            request_id, admin_id=current_user['id']
        )
        await database.audit.log_action(
            'entity_request', request_id, 'approve',
            user_id=current_user['id'], after=result,
        )
        return result
    except database.entity_requests.RequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_requests_page.post('/{request_id}/reject')
async def reject_request(
    request_id: uuid.UUID,
    body: EntityRequestReject,
    current_user: deps.AdminUser = None,
):
    try:
        reason = (body.reason or '').strip()
        if not reason:
            raise HTTPException(
                status_code=400, detail='Rejection reason is required'
            )
        request = await database.entity_requests.reject_request(
            request_id, reason=reason, admin_id=current_user['id']
        )
        await database.audit.log_action(
            'entity_request', request_id, 'reject',
            user_id=current_user['id'], after=request,
        )
        return request
    except HTTPException:
        raise
    except database.entity_requests.RequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
