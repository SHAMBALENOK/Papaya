"""Запросы представителей на отсутствующие олимпиады, сезоны и профили.

Представитель не создаёт сущности каталога напрямую — он описывает, чего не
хватает. Администратор видит очередь, проверяет дубли и создаёт сущность
одобрением запроса. Это одновременно и модерация, и защита каталога от
дублей: одна олимпиада может быть заведена разными вузами под разными
названиями.
"""

import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app import database
from app.caching.main import cache_user_after_write, get_redis
from app.core import deps
from app.core.cache_guard import safe_cache_write
from app.models.entity_requests import ENTITY_TYPES, REQUEST_STATUSES
from app.routers.docs import ATTACHMENT_EXTENSIONS, save_uploaded_document
from app.schemas.urls import ExternalUrl

university_requests_page = APIRouter(tags=['entity-requests'])
admin_requests_page = APIRouter(prefix='/admin/entity-requests', tags=['entity-requests'])

logger = logging.getLogger('papaya.entity_requests')

#: Какие поля будущей сущности можно передать в запросе. Остальное
#: отбрасывается: запрос — описание, а не способ записать произвольные данные.
_ALLOWED_PAYLOAD = {
    'OLYMPIAD': {'official_url', 'organizer'},
    'SEASON': set(),
    'PROFILE': {'rsosh_level'},
    'UNIVERSITY': {
        'short_name', 'website', 'preview_image', 'image', 'description',
        'become_representative', 'contact_email',
        'representative_justification',
    },
}


class EntityRequestCreate(BaseModel):
    entity_type: str = Field(description='OLYMPIAD | SEASON | PROFILE')
    name: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    payload: dict | None = None


class EntityRequestReject(BaseModel):
    reason: str


class UniversityProposalCreate(BaseModel):
    """Предложка университета от любого авторизованного пользователя."""

    name: str
    short_name: str | None = None
    description: str | None = None
    website: ExternalUrl = None
    preview_image: ExternalUrl = None
    image: ExternalUrl = None
    #: Осознанное согласие стать представителем созданного вуза. Раньше роль
    #: выдавалась автоматически при одобрении предложки; теперь — только если
    #: пользователь поставил галочку и заполнил контакт.
    become_representative: bool = False
    contact_email: EmailStr | None = None
    representative_justification: str | None = None

    @field_validator('name')
    @classmethod
    def _check_name(cls, v):
        v = (v or '').strip()
        if not v:
            raise ValueError('name is required')
        return v

    @model_validator(mode='after')
    def _check_representative_fields(self):
        if self.become_representative and not self.contact_email:
            raise ValueError(
                'contact_email is required when become_representative is set'
            )
        return self


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
        if entity_type == 'UNIVERSITY':
            # Новый университет вуз не «запрашивает»: предложку подаёт любой
            # пользователь через /university-requests, иначе представитель
            # мог бы создать вуз от имени своего.
            raise HTTPException(
                status_code=400,
                detail='Use /university-requests to propose a university',
            )
        name = (body.name or '').strip()
        if not name:
            raise HTTPException(status_code=400, detail='Name is required')
        if entity_type in ('SEASON', 'PROFILE') and body.parent_id is None:
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


@university_requests_page.post(
    '/university-requests',
    status_code=201,
)
async def create_university_proposal(
    body: UniversityProposalCreate,
    current_user: dict = Depends(deps.get_current_user),
):
    """Предложить университет в каталог.

    Доступно обычному пользователю. Если отмечено «хочу стать представителем»,
    после одобрения администратор назначит роль представителя созданного вуза;
    без галочки предложка только добавляет вуз в каталог.
    """
    try:
        payload = {
            'short_name': (body.short_name or '').strip() or None,
            'description': (body.description or '').strip() or None,
            'website': body.website,
            'preview_image': body.preview_image,
            'image': body.image,
            'become_representative': body.become_representative,
            'contact_email': (
                str(body.contact_email) if body.contact_email else None
            ),
            'representative_justification': (
                (body.representative_justification or '').strip() or None
            ),
        }
        request = await database.entity_requests.create_request(
            {
                'entity_type': 'UNIVERSITY',
                'name': body.name,
                'description': (body.description or '').strip() or None,
                'payload': _clean_payload('UNIVERSITY', payload),
                'university_id': None,
                'parent_id': None,
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


@university_requests_page.get('/university-requests/my')
async def list_my_university_proposals(
    current_user: dict = Depends(deps.get_current_user),
):
    """Свои предложки университетов: профиль показывает статус рассмотрения."""
    try:
        requests, _total = await database.entity_requests.list_requests(
            entity_type='UNIVERSITY',
            created_by=current_user['id'],
            limit=20,
        )
        return {'requests': requests}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _get_request_for_user(request_id, current_user) -> dict:
    request = await database.entity_requests.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail='Request not found')
    is_author = str(request.get('created_by') or '') == str(
        current_user.get('id') or ''
    )
    if not is_author and current_user.get('role') != deps.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail='Permission denied')
    return request


@university_requests_page.get('/entity-requests/{request_id}/attachments')
async def list_request_attachments(
    request_id: uuid.UUID,
    current_user: dict = Depends(deps.get_current_user),
):
    """Вложения к заявке: видит автор заявки и администратор."""
    try:
        await _get_request_for_user(request_id, current_user)
        docs = await database.docs.list_docs(entity_request_id=request_id)
        return {'attachments': docs}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_requests_page.post(
    '/entity-requests/{request_id}/attachments',
    status_code=201,
)
async def upload_request_attachment(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    kind: str | None = Form(default=None),
    current_user: dict = Depends(deps.get_current_user),
):
    """Приложить подтверждающий документ или фото к заявке."""
    try:
        await _get_request_for_user(request_id, current_user)
        record = await save_uploaded_document(
            file,
            doc_type='ATTACHMENT',
            name=name,
            uploaded_by=current_user['id'],
            entity_request_id=str(request_id),
            allowed_extensions=ATTACHMENT_EXTENSIONS,
            metadata={'kind': 'representative_photo'} if kind == 'photo' else None,
        )
        await database.audit.log_action(
            'doc', record['id'], 'upload',
            user_id=current_user['id'], after=record,
        )
        return record
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
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Создать сущность по запросу. Дубль — 409, запрос остаётся в очереди."""
    try:
        result = await database.entity_requests.approve_request(
            request_id, admin_id=current_user['id']
        )
        request = result['request']
        # Предложка университета: представителем созданного вуза автор
        # становится только при явном согласии в заявке. Роль не понижается,
        # если пользователь уже представитель другого университета или
        # администратор.
        wants_representative = bool(
            (request.get('payload') or {}).get('become_representative')
        )
        if (
            request.get('entity_type') == 'UNIVERSITY'
            and request.get('created_by')
            and wants_representative
        ):
            author = await database.users.find_user_by_id(request['created_by'])
            if author and author.get('role') == 'USER':
                updated = await database.users.apply_role_guarded(
                    author['id'],
                    'EDITOR',
                    university_id=result['entity_id'],
                )
                if isinstance(updated, dict):
                    await safe_cache_write(cache_user_after_write(r, updated))
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
