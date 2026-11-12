import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app import database
from app.core import deps

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
async def review_application(app_id: uuid.UUID, body: ReviewRequest, current_user: dict = Depends(deps.require_admin)):
    try:
        if body.status not in ('approved', 'rejected'):
            raise HTTPException(status_code=400, detail='status must be approved or rejected')
        app = await database.representative.review_application(app_id, body.status, current_user['id'], body.rejection_reason)
        if not app:
            raise HTTPException(status_code=404, detail='Application not found')
        # if approved, set user role to EDITOR with university
        if body.status == 'approved':
            from app.database import users as users_db
            a = await database.representative.get_application(app_id)
            await users_db.apply_role_guarded(a['user_id'], 'EDITOR', university_id=a['university_id'])
        await database.audit.log_action('representative_application', app_id, 'review', user_id=current_user['id'], after=app)
        return app
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')