"""Каталог университетов и управление связями БВИ.

Сценарий Papaya: школьник открывает каталог, находит свой университет и видит
олимпиады, дающие БВИ. Поэтому чтение каталога публично (регистрация не
нужна), а запись каталога — только у администратора. Университеты создаёт
администратор: РСОШ — источник каталога **олимпиад**, а не университетов.

Представитель университета (``EDITOR`` + ``university_id``) управляет связями
**своего** университета: выбирает существующую олимпиаду из каталога и
заявляет, что вуз даёт за неё БВИ. Новую олимпиаду он не создаёт, а
подтверждённую связь не может убрать сам — это делает администратор.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import database, schemas
from app.core import deps

universities_page = APIRouter(
    prefix='/universities',
    tags=['universities'],
)

logger = logging.getLogger('papaya.universities')


class UniversityListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    short_name: str | None = None
    description: str | None = None
    website: str | None = None
    preview_image: str | None = None
    image: str | None = None


class UniversitiesResponse(BaseModel):
    universities: List[UniversityListItem]


def _serialize(university: dict) -> dict:
    return {
        'id': university.get('id'),
        'name': university.get('name'),
        'short_name': university.get('short_name'),
        'description': university.get('description'),
        'website': university.get('website'),
        'preview_image': university.get('preview_image'),
        'image': university.get('image'),
    }


@universities_page.get(
    '',
    response_model=UniversitiesResponse,
    responses={
        200: {'description': 'Каталог университетов'},
        500: {'description': 'Internal server error'},
    },
)
async def list_universities(
    search: str | None = Query(
        default=None,
        description='Поиск по названию, краткому названию и описанию',
    ),
    limit: int | None = Query(default=None, ge=1, le=500),
):
    """Каталог университетов — публичное чтение без авторизации."""
    try:
        universities = await database.universities.list_universities(
            search=search,
            limit=limit,
        )
        return {'universities': [_serialize(item) for item in universities]}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}',
    response_model=schemas.universities.UniversityResponse,
    responses={
        200: {'description': 'University details'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def university_details(university_id: uuid.UUID):
    """Страница университета."""
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        return university
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}/olympiads',
    responses={
        200: {'description': 'Олимпиады, дающие БВИ в университете'},
        400: {'description': 'Access token required to view pending requests'},
        403: {'description': 'Pending requests are visible to own university only'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def university_olympiads(
    university_id: uuid.UUID,
    include_pending: bool = Query(
        default=False,
        description='Показать неподтверждённые заявки (своя организация/админ)',
    ),
    current_user: deps.OptionalUser = None,
):
    """Олимпиады, дающие БВИ в этом университете.

    Гость получает подтверждённые связи — этого достаточно основному
    сценарию. Неподтверждённые заявки видны представителю своего университета
    и администратору: это рабочий процесс модерации, а не публичный факт.
    """
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')

        show_pending = False
        if include_pending:
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail='Access token required to view pending requests',
                )
            if not deps.can_manage_university(current_user, university_id):
                raise HTTPException(
                    status_code=403,
                    detail='You can only view pending requests of your own university',
                )
            show_pending = True

        olympiads = await database.bvi.list_olympiads_for_university(
            university_id,
            include_pending=show_pending,
        )
        return {'olympiads': olympiads}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/add_university',
    response_model=schemas.universities.UniversityResponse,
    status_code=201,
    responses={
        201: {'description': 'University created'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        409: {'description': 'University with this name already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def add_university(
    university: schemas.universities.UniversityCreate,
    current_user: deps.AdminUser = None,
):
    """Создать университет (вручную, администратором)."""
    try:
        created = await database.universities.add_university(university.model_dump())
        if not created:
            raise HTTPException(
                status_code=409,
                detail='University with this name already exists',
            )
        return created
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/edit_university/{university_id}',
    response_model=schemas.universities.UniversityResponse,
    responses={
        200: {'description': 'University updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'University not found'},
        409: {'description': 'University with this name already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def edit_university(
    university_id: uuid.UUID,
    university: schemas.universities.UniversityUpdate,
    current_user: deps.AdminUser = None,
):
    """Изменить университет (администратором)."""
    try:
        update_data = university.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')
        updated = await database.universities.edit_university(
            university_id,
            update_data,
        )
        if not updated:
            existing = await database.universities.get_university(university_id)
            if not existing:
                raise HTTPException(status_code=404, detail='University not found')
            raise HTTPException(
                status_code=409,
                detail='University with this name already exists',
            )
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/bvi',
    response_model=schemas.bvi.BviLinkResponse,
    status_code=201,
    responses={
        201: {'description': 'BVI request created or already exists'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'University or olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def request_bvi(
    university_id: uuid.UUID,
    body: schemas.bvi.BviLinkRequest,
    current_user: deps.ManageUniversity = None,
):
    """Заявить, что университет даёт БВИ за существующую олимпиаду.

    Связь создаётся в статусе ``PENDING`` и становится публичной после
    подтверждения администратором. Права проверяются для конкретного вуза:
    представитель одного университета не может заявить связь за другой.
    """
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        olympiad = await database.olympiads.get_olympiad(body.olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')

        link = await database.bvi.request_bvi_link(
            body.olympiad_id,
            university_id,
            requested_by=current_user.get('id'),
        )
        return link
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/bvi/remove',
    responses={
        200: {'description': 'BVI request removed'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'BVI link not found'},
        409: {'description': 'Confirmed link can only be revoked by an administrator'},
        500: {'description': 'Internal server error'},
    },
)
async def remove_bvi(
    university_id: uuid.UUID,
    body: schemas.bvi.BviLinkRequest,
    current_user: deps.ManageUniversity = None,
):
    """Убрать связь БВИ.

    Бизнес-правило: подтверждённая администратором связь — это публичный
    факт, поэтому представитель не может убрать её одним запросом. Он может
    отозвать только собственную неподтверждённую заявку; снять подтверждение
    (или удалить связь целиком) может администратор.
    """
    try:
        link = await database.bvi.get_link(body.olympiad_id, university_id)
        if not link:
            raise HTTPException(status_code=404, detail='BVI link not found')
        if (
            link['status'] == 'CONFIRMED'
            and current_user.get('role') != deps.ROLE_ADMIN
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    'Связь подтверждена администратором: снять подтверждение '
                    'может только администратор'
                ),
            )

        removed = await database.bvi.delete_bvi_link(body.olympiad_id, university_id)
        if not removed:
            raise HTTPException(status_code=404, detail='BVI link not found')
        return {'status': 'removed', 'olympiad_id': str(body.olympiad_id)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/bvi/{olympiad_id}/status',
    response_model=schemas.bvi.BviLinkResponse,
    responses={
        200: {'description': 'BVI link status updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'BVI link not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def set_bvi_status(
    university_id: uuid.UUID,
    olympiad_id: uuid.UUID,
    body: schemas.bvi.BviStatusUpdate,
    current_user: deps.AdminUser = None,
):
    """Подтвердить или снять связь БВИ (модерация, администратор)."""
    try:
        link = await database.bvi.set_bvi_status(
            olympiad_id,
            university_id,
            body.status,
            confirmed_by=current_user.get('id'),
        )
        if not link:
            raise HTTPException(status_code=404, detail='BVI link not found')
        return link
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
