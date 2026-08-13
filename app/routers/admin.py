from fastapi import APIRouter, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from app.caching.main import get_redis

import app.middlewares.tokenz.main as tokenz
from app.database.database import get_db
from app import schemas, database
from app.middlewares.task_queue import run_task
from typing import Annotated
import json

admin_page = APIRouter(
    prefix='/admin',
    tags=['administration']
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _require_admin(r: aioredis.Redis, db: AsyncSession, access_jwt, refresh_jwt):
    """Проверяет JWT и роль ADMIN. Возвращает dict администратора
    (из кэша или БД) либо бросает 401/403."""
    jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
    cache_key = f"user:{jwt_data.get('sub')}:object"
    cached = await r.get(cache_key)
    if cached:
        admin_obj = json.loads(cached)
    else:
        admin_obj = await run_task(database.users.find_user_by_id, jwt_data.get('sub'))
        if not admin_obj:
            raise HTTPException(status_code=403, detail='permission denied')
        await r.set(cache_key, json.dumps(admin_obj), ex=600)
    if admin_obj.get('role') != 'ADMIN':
        raise HTTPException(status_code=403, detail='permission denied')
    return admin_obj


def _serialize_user(u: dict) -> dict:
    """Пользователь для админ-панели: роль и активность обязательны."""
    return {
        'id': u.get('id'),
        'name': u.get('name'),
        'surname': u.get('surname'),
        'email': u.get('email'),
        'role': u.get('role'),
        'isActive': u.get('isActive'),
        'createdAt': u.get('createdAt'),
    }


def _serialize_event(e: dict) -> dict:
    return {
        'id': e.get('id'),
        'owner': e.get('owner'),
        'name': e.get('name'),
        'disc': e.get('disc'),
        'preview_picture': e.get('preview_picture'),
        'picture': e.get('picture'),
        'isActive': e.get('isActive'),
        'createdAt': e.get('createdAt'),
        'updatedAt': e.get('updatedAt'),
    }


# ---------------------------------------------------------------------------
# Списки (данные для страницы #/admin)
# ---------------------------------------------------------------------------

@admin_page.get('/users')
async def list_users(
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Все пользователи с ролями и статусом активности."""
    try:
        admin_obj = await _require_admin(r, db, access_jwt, refresh_jwt)
        users_cache_key = f"user:{admin_obj.get('id')}:users"
        cached = await r.get(users_cache_key)
        if cached:
            users = json.loads(cached)
        else:
            quantity = await run_task(database.users.get_amount_of_users)
            users = await run_task(database.users.show_random_users, quantity)
            await r.set(users_cache_key, json.dumps(users), ex=600)
        return JSONResponse(status_code=200, content={
            'users': [_serialize_user(u) for u in users],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get('/events')
async def list_events(
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Все события со статусом активности (для архивирования)."""
    try:
        admin_obj = await _require_admin(r, db, access_jwt, refresh_jwt)
        events_cache_key = f"user:{admin_obj.get('id')}:events"
        cached = await r.get(events_cache_key)
        if cached:
            events = json.loads(cached)
        else:
            quantity = await run_task(database.events.get_amount_of_events)
            events = await run_task(database.events.show_random_events, quantity)
            await r.set(events_cache_key, json.dumps(events), ex=600)
        return JSONResponse(status_code=200, content={
            'events': [_serialize_event(e) for e in events],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------

@admin_page.get(
    '/ban/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def ban(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Блокировка пользователя (isActive = False)."""
    try:
        await _require_admin(r, db, access_jwt, refresh_jwt)
        await r.delete(f"user:{user_id}:object")
        updated_user = await run_task(database.users.edit_user, user_id, {'isActive': False})
        if not updated_user:
            raise HTTPException(status_code=404, detail='User not found')
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/unban/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def unban(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Разблокировка пользователя (isActive = True)."""
    try:
        await _require_admin(r, db, access_jwt, refresh_jwt)
        updated_user = await run_task(database.users.edit_user, user_id, {'isActive': True})
        if not updated_user:
            raise HTTPException(status_code=404, detail='User not found')
        await r.set(f"user:{user_id}:object", json.dumps(updated_user), ex=600)
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/archive_event/{event_id}',
    response_model=schemas.events.EventResponse,
)
async def archive_event(
        event_id: str,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Перенос события в архив (isActive = False)."""
    try:
        await _require_admin(r, db, access_jwt, refresh_jwt)
        await r.delete(f"event:{event_id}")
        updated_event = await run_task(database.events.edit_event, event_id, {'isActive': False})
        if not updated_event:
            raise HTTPException(status_code=404, detail='Event not found')
        return updated_event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/grant_admin/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def grant_admin(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Назначение роли ADMIN."""
    try:
        await _require_admin(r, db, access_jwt, refresh_jwt)
        user_cache_key = f"user:{user_id}:object"
        cached = await r.get(user_cache_key)
        if cached:
            to_user = json.loads(cached)
        else:
            to_user = await run_task(database.users.find_user_by_id, user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == 'ADMIN':
            raise HTTPException(status_code=403, detail='permission denied: user is already ADMIN')
        updated_user = await run_task(database.users.edit_user, user_id, {'role': 'ADMIN'})
        await r.set(user_cache_key, json.dumps(updated_user), ex=600)
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/demote_admin/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def demote_admin(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Снятие роли ADMIN (до USER)."""
    try:
        await _require_admin(r, db, access_jwt, refresh_jwt)
        user_cache_key = f"user:{user_id}:object"
        cached = await r.get(user_cache_key)
        if cached:
            to_user = json.loads(cached)
        else:
            to_user = await run_task(database.users.find_user_by_id, user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == 'USER':
            raise HTTPException(status_code=403, detail='permission denied: user is already USER')
        updated_user = await run_task(database.users.edit_user, user_id, {'role': 'USER'})
        await r.set(user_cache_key, json.dumps(updated_user), ex=600)
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')