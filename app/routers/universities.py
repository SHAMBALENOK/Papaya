"""Каталог университетов.

Чтение каталога публично (регистрация не нужна), запись — только у
администратора. Льготы университета живут в правилах (``/benefits``), а не в
отдельной сущности БВИ: одна модель, одна модерация.
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
    response_model=schemas.universities.UniversityPublicResponse,
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
        await database.audit.log_action(
            'university', created['id'], 'create',
            user_id=current_user['id'], after=created,
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
        await database.audit.log_action(
            'university', university_id, 'update',
            user_id=current_user['id'], after=updated,
        )
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
