import uuid
import logging
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app import database
from app.caching.main import cache_user_after_write, get_redis
from app.core import deps
from app.core.cache_guard import safe_cache_write
from app.routers.docs import ATTACHMENT_EXTENSIONS, save_uploaded_document

rep_apps_page = APIRouter(prefix='/representative-applications', tags=['representative'])
admin_rep_page = APIRouter(tags=['representative'])
applications_page = APIRouter(prefix='/applications', tags=['representative'])

logger = logging.getLogger('papaya.representative')


class ApplicationCreate(BaseModel):
    university_id: str
    justification: str | None = None


class ReviewRequest(BaseModel):
    status: str
    rejection_reason: str | None = None


@rep_apps_page.post('')
async def create_application(body: ApplicationCreate, current_user: dict = Depends(deps.get_current_user)):
    try:
        university = await database.universities.get_university(body.university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        app = await database.representative.create_application(current_user['id'], body.university_id, body.justification)
        await database.audit.log_action(
            'representative_application', app['id'], 'create',
            user_id=current_user['id'], after=app,
        )
        return app
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@applications_page.post('')
async def create_application_alias(body: ApplicationCreate, current_user: dict = Depends(deps.get_current_user)):
    return await create_application(body, current_user)


@applications_page.get('/my')
async def list_my_applications(current_user: dict = Depends(deps.get_current_user)):
    """Свои заявки представителя: профиль показывает статус рассмотрения."""
    try:
        apps = await database.representative.list_applications(user_id=current_user['id'])
        return {'applications': apps}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _application_for_user(app_id, current_user) -> dict:
    application = await database.representative.get_application(app_id)
    if not application:
        raise HTTPException(status_code=404, detail='Application not found')
    is_owner = str(application.get('user_id') or '') == str(
        current_user.get('id') or ''
    )
    if not is_owner and current_user.get('role') != deps.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail='Permission denied')
    return application


@rep_apps_page.get('/{app_id}/attachments')
async def list_application_attachments(
    app_id: uuid.UUID,
    current_user: dict = Depends(deps.get_current_user),
):
    """Вложения к заявке представителя: автор и администратор."""
    try:
        await _application_for_user(app_id, current_user)
        docs = await database.docs.list_docs(representative_application_id=app_id)
        return {'attachments': docs}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@rep_apps_page.post('/{app_id}/attachments', status_code=201)
async def upload_application_attachment(
    app_id: uuid.UUID,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    current_user: dict = Depends(deps.get_current_user),
):
    """Приложить документ или фото к заявке представителя."""
    try:
        await _application_for_user(app_id, current_user)
        record = await save_uploaded_document(
            file,
            doc_type='ATTACHMENT',
            name=name,
            uploaded_by=current_user['id'],
            representative_application_id=str(app_id),
            allowed_extensions=ATTACHMENT_EXTENSIONS,
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


@admin_rep_page.get('/admin/representative-applications')
async def list_applications(status: str | None = None, current_user: dict = Depends(deps.require_admin)):
    try:
        apps = await database.representative.list_applications(status)
        return {'applications': apps}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_rep_page.get('/admin/audit')
async def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(deps.require_admin),
):
    """Журнал действий с фильтрами по сущности, id и действию."""
    try:
        logs = await database.audit.list_audit(
            entity_type, entity_id, action, limit=limit, offset=offset
        )
        total = await database.audit.count_audit(entity_type, entity_id, action)
        return {'logs': logs, 'total': total}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_rep_page.post('/admin/representative-applications/{app_id}/review')
async def review_application(
    app_id: uuid.UUID,
    body: ReviewRequest,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(deps.require_admin),
):
    try:
        if body.status not in ('approved', 'rejected'):
            raise HTTPException(status_code=400, detail='status must be approved or rejected')
        app = await database.representative.review_application(app_id, body.status, current_user['id'], body.rejection_reason)
        if not app:
            raise HTTPException(status_code=404, detail='Application not found')
        # if approved, set user role to EDITOR with university
        if body.status == 'approved':
            from app.database import users as users_db
            updated = await users_db.apply_role_guarded(
                app['user_id'], 'EDITOR', university_id=app['university_id']
            )
            if isinstance(updated, dict):
                # Без сброса кэша пользователь ещё до истечения TTL не увидел бы
                # раздел «Мой университет».
                await safe_cache_write(cache_user_after_write(r, updated))
        await database.audit.log_action('representative_application', app_id, 'review', user_id=current_user['id'], after=app)
        return app
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')