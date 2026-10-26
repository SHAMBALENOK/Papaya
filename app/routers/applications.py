"""Заявки на роль представителя вуза (ТЗ §3.4).

Пользователь подаёт заявку с указанием вуза и обоснованием. Администратор
рассматривает её: одобрение выдаёт роль ``EDITOR`` с привязкой к вузу через тот
же защищённый путь, что и ручное назначение. Отклонение сохраняется с причиной.

Заявка не даёт прав сама по себе: до одобрения её автор — обычный ``USER``.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query

from app import database, schemas
from app.core import audit, deps
from app.database.applications import APPLICATION_STATUSES
from app.schemas.applications import APPLICATION_DECISIONS

applications_page = APIRouter(
    prefix='/applications',
    tags=['applications'],
)

logger = logging.getLogger('papaya.applications')


@applications_page.post(
    '',
    response_model=schemas.applications.ApplicationItem,
    status_code=201,
    responses={
        201: {'description': 'Заявка подана'},
        401: {'description': 'Access token missing'},
        404: {'description': 'University not found'},
        409: {'description': 'Активная заявка на этот вуз уже есть'},
        500: {'description': 'Internal server error'},
    },
)
async def submit_application(
    body: schemas.applications.ApplicationCreate,
    current_user: deps.CurrentUser = None,
):
    """Подать заявку на роль представителя вуза.

    Заявка подаётся от имени текущего пользователя: клиент не может подать её
    за другого. Одна активная заявка на пару (пользователь, вуз).
    """
    try:
        university = await database.universities.get_university(body.university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        application = await database.applications.submit_application(
            current_user.get('id'),
            body.university_id,
            motivation=body.motivation,
        )
        if application is None:
            raise HTTPException(
                status_code=409,
                detail='Заявка на этот университет уже подана',
            )
        return application
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@applications_page.get(
    '/mine',
    response_model=schemas.applications.ApplicationsResponse,
    responses={
        200: {'description': 'Свои заявки'},
        401: {'description': 'Access token missing'},
        500: {'description': 'Internal server error'},
    },
)
async def my_applications(current_user: deps.CurrentUser = None):
    """Свои заявки: пользователь видит их статус."""
    try:
        applications = await database.applications.list_applications(
            user_id=current_user.get('id')
        )
        total = await database.applications.count_applications(
            user_id=current_user.get('id')
        )
        return {'applications': applications, 'total': total}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@applications_page.get(
    '',
    response_model=schemas.applications.ApplicationsResponse,
    responses={
        200: {'description': 'Очередь заявок'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_applications(
    status: str | None = Query(default='PENDING'),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    """Очередь заявок для администратора (по умолчанию — ожидающие)."""
    try:
        if status is not None and status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail='Unknown status')
        applications = await database.applications.list_applications(
            status=status, limit=limit, offset=offset
        )
        total = await database.applications.count_applications(status=status)
        return {'applications': applications, 'total': total}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@applications_page.post(
    '/{application_id}/decision',
    response_model=schemas.applications.ApplicationItem,
    responses={
        200: {'description': 'Решение по заявке принято'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Application not found'},
        409: {'description': 'Заявка уже рассмотрена'},
        500: {'description': 'Internal server error'},
    },
)
async def decide_application(
    application_id: uuid.UUID,
    body: schemas.applications.ApplicationDecision,
    current_user: deps.AdminUser = None,
):
    """Одобрить или отклонить заявку (администратор).

    Одобрение выдаёт роль представителя с привязкой к вузу заявки. Отклонение
    сохраняется с причиной. Повторное решение невозможно (409).
    """
    try:
        if body.decision not in APPLICATION_DECISIONS:
            raise HTTPException(status_code=400, detail='Unknown decision')
        outcome = await database.applications.review_application(
            application_id,
            body.decision,
            reviewer_id=current_user.get('id'),
            note=body.note,
        )
        if outcome is None:
            raise HTTPException(status_code=404, detail='Application not found')
        if isinstance(outcome, str):
            # Роль выдать не удалось (например, последний администратор).
            # Заявка при этом осталась в ожидании — решение можно повторить
            # позже, когда ограничение перестанет мешать.
            raise HTTPException(
                status_code=409,
                detail='Не удалось назначить роль представителя, заявка осталась в ожидании (ограничение ролей)',
            )
        await audit.audit(
            'application_' + body.decision.lower(),
            actor_id=current_user.get('id'),
            target_type='representative_application',
            target_id=application_id,
            note=body.note,
        )
        return outcome
    except HTTPException:
        raise
    except database.applications.ApplicationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
