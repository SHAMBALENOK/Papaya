import logging
import uuid
from typing import Annotated, List

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import database, schemas
from app.caching.main import (
    cache_event_after_write,
    cache_user_after_write,
    get_cached_events,
    get_cached_user,
    get_cached_users,
    get_redis,
)
from app.core.cache_guard import safe_cache_write
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz


admin_page = APIRouter(
    prefix='/admin',
    tags=['administration'],
)

logger = logging.getLogger('papaya.admin')


async def _require_admin(
    r: aioredis.Redis,
    access_jwt: str | None,
    refresh_jwt: str | None,
) -> dict:
    """Проверить JWT и роль ADMIN, используя актуальную версию пользователя."""
    jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
    user_id = jwt_data.get('sub')
    admin_obj = await get_cached_user(
        r,
        user_id,
        lambda: database.users.find_user_by_id(user_id),
    )
    if not admin_obj or admin_obj.get('role') != 'ADMIN':
        raise HTTPException(status_code=403, detail='permission denied')
    return admin_obj


class AdminUserListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    surname: str | None = None
    email: str | None = None
    role: str | None = None
    isActive: bool | None = None
    createdAt: str | None = None


class AdminUsersResponse(BaseModel):
    users: List[AdminUserListItem]


class AdminEventListItem(BaseModel):
    id: str | None = None
    owner: str | None = None
    name: str | None = None
    disc: str | None = None
    preview_picture: str | None = None
    picture: str | None = None
    isActive: bool | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class AdminEventsResponse(BaseModel):
    events: List[AdminEventListItem]


def _serialize_user(user: dict) -> dict:
    """Пользователь для админ-панели: роль и активность обязательны."""
    return {
        'id': user.get('id'),
        'name': user.get('name'),
        'surname': user.get('surname'),
        'email': user.get('email'),
        'role': user.get('role'),
        'isActive': user.get('isActive'),
        'createdAt': user.get('createdAt'),
    }


def _serialize_event(event: dict) -> dict:
    return {
        'id': event.get('id'),
        'owner': event.get('owner'),
        'name': event.get('name'),
        'disc': event.get('disc'),
        'preview_picture': event.get('preview_picture'),
        'picture': event.get('picture'),
        'isActive': event.get('isActive'),
        'createdAt': event.get('createdAt'),
        'updatedAt': event.get('updatedAt'),
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
async def list_users(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Все пользователи, включая заблокированных."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        users = await get_cached_users(
            r,
            True,
            lambda: database.users.list_users(include_inactive=True),
        )
        return JSONResponse(
            status_code=200,
            content={'users': [_serialize_user(user) for user in users]},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


@admin_page.get(
    '/events',
    response_model=AdminEventsResponse,
    responses={
        200: {'description': 'List of all events including archived'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_events(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Все события, включая архивные."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        events = await get_cached_events(
            r,
            'all',
            lambda: database.events.list_events(active_only=False),
        )
        return JSONResponse(
            status_code=200,
            content={'events': [_serialize_event(event) for event in events]},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


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
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Заблокировать пользователя (isActive = False)."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        updated_user = await database.users.edit_user(user_id, {'isActive': False})
        if not updated_user:
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated_user))
        return updated_user
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


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
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Разблокировать пользователя (isActive = True)."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        updated_user = await database.users.edit_user(user_id, {'isActive': True})
        if not updated_user:
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated_user))
        return updated_user
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


@admin_page.post(
    '/archive_event/{event_id}',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'Event archived successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Event not found'},
        500: {'description': 'Internal server error'},
    },
)
async def archive_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Перенести событие в архив (isActive = False)."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        updated_event = await database.events.edit_event(
            event_id,
            {'isActive': False},
        )
        if not updated_event:
            raise HTTPException(status_code=404, detail='Event not found')
        # Обновляет карточку события и меняет поколение всех списков. Поэтому
        # каталог сразу скрывает архивное событие, а админка видит его архивным.
        await safe_cache_write(cache_event_after_write(r, updated_event))
        return updated_event
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


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
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Назначить роль ADMIN."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        to_user = await get_cached_user(
            r,
            user_id,
            lambda: database.users.find_user_by_id(user_id),
        )
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == 'ADMIN':
            raise HTTPException(
                status_code=409,
                detail='User is already ADMIN',
            )

        updated_user = await database.users.edit_user(user_id, {'role': 'ADMIN'})
        if not updated_user:
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated_user))
        return updated_user
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


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
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Снять роль ADMIN до USER."""
    try:
        await _require_admin(r, access_jwt, refresh_jwt)
        to_user = await get_cached_user(
            r,
            user_id,
            lambda: database.users.find_user_by_id(user_id),
        )
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == 'USER':
            raise HTTPException(
                status_code=409,
                detail='User is already USER',
            )

        updated_user = await database.users.edit_user(user_id, {'role': 'USER'})
        if not updated_user:
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated_user))
        return updated_user
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
