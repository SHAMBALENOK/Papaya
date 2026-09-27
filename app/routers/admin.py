"""Администрирование Papaya.

Администратор отвечает за каталог и его наполнение:

- пользователи: блокировка, роли, привязка представителя к университету;
- олимпиады: архивирование/возврат из архива, ручное создание и правка;
- заявки БВИ: подтверждение и снятие связей университет ↔ олимпиада.

Все маршруты требуют роль ``ADMIN``: проверка общая и живёт в
``app.core.deps.require_admin``.
"""

import logging
import uuid
from typing import List

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import database, schemas
from app.caching.main import cache_user_after_write, get_redis
from app.core import deps
from app.core.cache_guard import safe_cache_write

admin_page = APIRouter(
    prefix='/admin',
    tags=['administration'],
)

logger = logging.getLogger('papaya.admin')


class AdminUserListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    surname: str | None = None
    email: str | None = None
    role: str | None = None
    university_id: str | None = None
    isActive: bool | None = None
    createdAt: str | None = None


class AdminUsersResponse(BaseModel):
    users: List[AdminUserListItem]


class AdminOlympiadListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    source_doc_id: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class AdminOlympiadsResponse(BaseModel):
    olympiads: List[AdminOlympiadListItem]


class AdminBviListItem(BaseModel):
    id: str | None = None
    university_id: str | None = None
    university_name: str | None = None
    olympiad_id: str | None = None
    olympiad_name: str | None = None
    status: str | None = None
    createdAt: str | None = None


class AdminBviResponse(BaseModel):
    links: List[AdminBviListItem]


class UniversityAssignment(BaseModel):
    """Привязка пользователя к университету (роль представителя).

    Пустой ``university_id`` отвязывает представителя от университета.
    """

    university_id: str | None = None


def _serialize_user(user: dict) -> dict:
    return {
        'id': user.get('id'),
        'name': user.get('name'),
        'surname': user.get('surname'),
        'email': user.get('email'),
        'role': user.get('role'),
        'university_id': user.get('university_id'),
        'isActive': user.get('isActive'),
        'createdAt': user.get('createdAt'),
    }


@admin_page.get(
    '/users',
    response_model=AdminUsersResponse,
    responses={
        200: {'description': 'List of all users including inactive'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_users(current_user: deps.AdminUser = None):
    """Все пользователи, включая заблокированных."""
    try:
        users = await database.users.list_users(include_inactive=True)
        return JSONResponse(
            status_code=200,
            content={'users': [_serialize_user(user) for user in users]},
        )
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.get(
    '/olympiads',
    response_model=AdminOlympiadsResponse,
    responses={
        200: {'description': 'Полный каталог олимпиад, включая архивные'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_olympiads(current_user: deps.AdminUser = None):
    """Каталог олимпиад включая архивные (вне актуального перечня РСОШ)."""
    try:
        olympiads = await database.olympiads.list_olympiads(status=None)
        return {
            'olympiads': [
                {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'status': item.get('status'),
                    'source_doc_id': item.get('source_doc_id'),
                    'createdAt': item.get('createdAt'),
                    'updatedAt': item.get('updatedAt'),
                }
                for item in olympiads
            ],
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.get(
    '/bvi',
    response_model=AdminBviResponse,
    responses={
        200: {'description': 'Заявки и подтверждённые связи БВИ'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_bvi_links(
    status: str | None = None,
    current_user: deps.AdminUser = None,
):
    """Очередь модерации: заявки университетов на связи БВИ."""
    try:
        links = await database.bvi.list_links(status=status)
        enriched: list[dict] = []
        for link in links:
            university = await database.universities.get_university(
                link['university_id']
            )
            olympiad = await database.olympiads.get_olympiad(link['olympiad_id'])
            enriched.append(
                {
                    'id': link.get('id'),
                    'university_id': link.get('university_id'),
                    'university_name': (university or {}).get('name'),
                    'olympiad_id': link.get('olympiad_id'),
                    'olympiad_name': (olympiad or {}).get('name'),
                    'status': link.get('status'),
                    'createdAt': link.get('createdAt'),
                }
            )
        return {'links': enriched}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _change_user(
    user_id: uuid.UUID,
    ins: dict,
    r: aioredis.Redis,
) -> dict:
    """Изменить пользователя и сбросить версионный кэш ролей.

    Роль читается через versioned-кэш Redis, поэтому после записи кэш обязан
    быть инвалидирован — иначе понижение прав не действует до истечения JWT.
    """
    updated = await database.users.edit_user(user_id, ins)
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    await safe_cache_write(cache_user_after_write(r, updated))
    return updated


@admin_page.post(
    '/ban/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User banned successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def ban(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Заблокировать пользователя (isActive = False)."""
    try:
        return await _change_user(user_id, {'isActive': False}, r)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/unban/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User unbanned successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def unban(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Разблокировать пользователя (isActive = True)."""
    try:
        return await _change_user(user_id, {'isActive': True}, r)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/grant_admin/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Admin role granted'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        409: {'description': 'User is already ADMIN'},
        500: {'description': 'Internal server error'},
    },
)
async def grant_admin(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Назначить роль ADMIN."""
    try:
        to_user = await database.users.find_user_by_id(user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == 'ADMIN':
            raise HTTPException(status_code=409, detail='User is already ADMIN')
        return await _change_user(user_id, {'role': 'ADMIN'}, r)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/demote_admin/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Admin role removed'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        409: {'description': 'User is already USER'},
        500: {'description': 'Internal server error'},
    },
)
async def demote_admin(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Снять роль ADMIN до USER."""
    try:
        to_user = await database.users.find_user_by_id(user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == 'USER':
            raise HTTPException(status_code=409, detail='User is already USER')
        return await _change_user(user_id, {'role': 'USER'}, r)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/university/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'University representative assigned or detached'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User or university not found'},
        500: {'description': 'Internal server error'},
    },
)
async def assign_university(
    user_id: uuid.UUID,
    payload: UniversityAssignment,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Привязать пользователя к университету (роль представителя).

    Пустой ``university_id`` отвязывает пользователя от университета.
    """
    try:
        if payload.university_id:
            university = await database.universities.get_university(
                payload.university_id
            )
            if not university:
                raise HTTPException(status_code=404, detail='University not found')
        return await _change_user(
            user_id,
            {'university_id': payload.university_id},
            r,
        )
    except HTTPException:
        raise
    except IntegrityError:
        logger.warning('University assignment conflict for user %s', user_id)
        raise HTTPException(status_code=404, detail='University not found')
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/archive_olympiad/{olympiad_id}',
    response_model=schemas.olympiads.OlympiadResponse,
    responses={
        200: {'description': 'Olympiad archived or restored'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def archive_olympiad(
    olympiad_id: uuid.UUID,
    archived: bool = True,
    current_user: deps.AdminUser = None,
):
    """Перевести олимпиаду в архив или вернуть в актуальный каталог.

    Архив означает «олимпиады нет в актуальном перечне РСОШ»: запись
    сохраняется, но исчезает из публичного каталога.
    """
    try:
        updated = await database.olympiads.edit_olympiad(
            olympiad_id,
            {'status': 'ARCHIVED' if archived else 'PUBLISHED'},
        )
        if not updated:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
