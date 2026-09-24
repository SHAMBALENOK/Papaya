"""Общие FastAPI-зависимости для REST API.

Востребованные списки/записи читаются из версионного Redis-кэша при помощи
``get_cached_user`` (как делают исторические роутеры), чтобы у всех
эндпоинтов была единая актуальная картина пользователя и единая логика
ошибок 401/403/404.

Роли: USER / ORGANIZATION_ADMIN / ADMIN. ``require_org_admin`` возвращает
пользователя; object-level проверка «это моя организация?» выполняется в
самом роутере по ``current_user['organization_id']``.
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, HTTPException

from app import database
from app.caching.main import get_cached_user, get_redis
import app.middlewares.tokenz.main as tokenz


async def get_current_user(
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
) -> dict:
    """Проверить JWT и вернуть актуальную запись пользователя (кэш/БД)."""
    jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
    user_id = jwt_data.get('sub')
    user_obj = await get_cached_user(
        r,
        user_id,
        lambda: database.users.find_user_by_id(user_id),
    )
    if not user_obj:
        raise HTTPException(status_code=404, detail='User not found')
    if user_obj.get('isActive') is False:
        raise tokenz.account_disabled_error()
    return user_obj


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Доступ только для платформенных администраторов (ADMIN)."""
    if current_user.get('role') != 'ADMIN':
        raise HTTPException(status_code=403, detail='Permission denied')
    return current_user


async def require_org_admin_or_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """org-admin обязан иметь организацию; ADMIN работает без ограничений."""
    if current_user.get('role') == 'ADMIN':
        return current_user
    if current_user.get('role') == 'ORGANIZATION_ADMIN':
        if not current_user.get('organization_id'):
            raise HTTPException(
                status_code=409,
                detail='Organization admin has no organization assigned',
            )
        return current_user
    raise HTTPException(status_code=403, detail='Permission denied')