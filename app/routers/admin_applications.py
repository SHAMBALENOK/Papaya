"""Заявки на роль администратора Papaya.

Подать заявку может любой авторизованный пользователь, у которого ещё нет
роли ``ADMIN``. Одобрение сразу выдаёт роль через единственную безопасную
точку ``apply_role_guarded``; одобрить собственную заявку нельзя.
"""

import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, field_validator

from app import database
from app.caching.main import cache_user_after_write, get_redis
from app.core import deps
from app.core.cache_guard import safe_cache_write
from app.database import users as users_db

public_page = APIRouter(prefix='/admin-applications', tags=['admin-applications'])
admin_page = APIRouter(prefix='/admin/admin-applications', tags=['admin-applications'])

logger = logging.getLogger('papaya.admin_applications')


class AdminApplicationCreate(BaseModel):
    contact_email: EmailStr
    motivation: str

    @field_validator('motivation')
    @classmethod
    def _check_motivation(cls, value):
        value = (value or '').strip()
        if not value:
            raise ValueError('motivation is required')
        return value


class AdminApplicationReject(BaseModel):
    reason: str

    @field_validator('reason')
    @classmethod
    def _check_reason(cls, value):
        value = (value or '').strip()
        if not value:
            raise ValueError('reason is required')
        return value


@public_page.post('', status_code=201)
async def create_application(
    body: AdminApplicationCreate,
    current_user: dict = Depends(deps.get_current_user),
):
    """Подать заявку. Одна pending-заявка на пользователя."""
    try:
        if current_user.get('role') == users_db.ROLE_ADMIN:
            raise HTTPException(
                status_code=409, detail='User is already an administrator'
            )
        application = await database.admin_applications.create_application(
            current_user['id'],
            str(body.contact_email),
            body.motivation,
        )
        await database.audit.log_action(
            'admin_application', application['id'], 'create',
            user_id=current_user['id'], after=application,
        )
        return application
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@public_page.get('/my')
async def list_my_applications(
    current_user: dict = Depends(deps.get_current_user),
):
    try:
        applications = await database.admin_applications.list_applications(
            user_id=current_user['id']
        )
        return {'applications': applications}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.get('')
async def list_applications(
    status: str | None = Query(default=None),
    current_user: deps.AdminUser = None,
):
    try:
        if status is not None and status not in ('pending', 'approved', 'rejected'):
            raise HTTPException(status_code=400, detail='Unknown status')
        applications = await database.admin_applications.list_applications(status)
        return {'applications': applications}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post('/{application_id}/approve')
async def approve_application(
    application_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Одобрить заявку и выдать роль ``ADMIN``.

    Свою заявку одобрять нельзя: иначе администратор мог бы обойти правило
    «роль меняет другой администратор». Роль выдаётся до закрытия заявки:
    если выдача не удалась, заявка остаётся в очереди, а не становится
    «одобренной без прав».
    """
    try:
        application = await database.admin_applications.get_application(application_id)
        if application is None:
            raise HTTPException(status_code=404, detail='Application not found')
        if application['status'] != 'pending':
            raise HTTPException(status_code=409, detail='Application is already reviewed')
        if str(application['user_id']) == str(current_user.get('id')):
            raise HTTPException(
                status_code=403, detail='Cannot approve your own application'
            )
        target = await database.users.find_user_by_id(application['user_id'])
        if target is None:
            raise HTTPException(status_code=404, detail='User not found')
        if target.get('role') == users_db.ROLE_ADMIN:
            raise HTTPException(
                status_code=409, detail='User is already an administrator'
            )

        updated = await users_db.apply_role_guarded(
            application['user_id'], users_db.ROLE_ADMIN, university_id=None
        )
        if isinstance(updated, str):
            raise HTTPException(status_code=409, detail=updated)
        if not updated:
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated))

        reviewed = await database.admin_applications.review_application(
            application_id, 'approved', current_user['id']
        )
        if reviewed is None:
            # Параллельный администратор уже закрыл заявку — роль выдана,
            # повторно её не трогаем.
            reviewed = await database.admin_applications.get_application(
                application_id
            )
        await database.audit.log_action(
            'admin_application', application_id, 'approve',
            user_id=current_user['id'], after=reviewed,
        )
        return reviewed
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post('/{application_id}/reject')
async def reject_application(
    application_id: uuid.UUID,
    body: AdminApplicationReject,
    current_user: deps.AdminUser = None,
):
    try:
        application = await database.admin_applications.get_application(application_id)
        if application is None:
            raise HTTPException(status_code=404, detail='Application not found')
        if application['status'] != 'pending':
            raise HTTPException(status_code=409, detail='Application is already reviewed')
        reviewed = await database.admin_applications.review_application(
            application_id, 'rejected', current_user['id'], body.reason
        )
        if reviewed is None:
            raise HTTPException(status_code=409, detail='Application is already reviewed')
        await database.audit.log_action(
            'admin_application', application_id, 'reject',
            user_id=current_user['id'], after=reviewed,
        )
        return reviewed
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
