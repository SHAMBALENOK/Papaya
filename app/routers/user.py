import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app import database, schemas
from app.caching.main import (
    cache_user_after_write,
    get_cached_user,
    get_redis,
)
from app.core import deps
from app.core.cache_guard import safe_cache_write


user_page = APIRouter(
    prefix='/user',
    tags=['users'],
)

logger = logging.getLogger('papaya.user')


@user_page.get(
    '/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User profile'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token or account is blocked'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def user_details(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(deps.get_current_user),
):
    """Профиль пользователя по id.

    Авторизация — общий механизм ``get_current_user``: валидный токен и
    незаблокированный автор. Раньше здесь стоял собственный ``jwt_check``,
    который не смотрел на ``isActive``: заблокированный продолжал бы читать
    профили действующей сессией. Читать профиль по id может любой
    вошедший пользователь — как и раньше.
    """
    try:
        user_obj = await get_cached_user(
            r,
            user_id,
            lambda: database.users.find_user_by_id(user_id),
        )
        if not user_obj:
            raise HTTPException(status_code=404, detail='User not found')
        return user_obj
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


@user_page.post(
    '/{user_id}/edit_info',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Profile updated'},
        401: {'description': 'Access token missing'},
        403: {
            'description': (
                'Cannot edit other user\'s profile, invalid token '
                'or account is blocked'
            ),
        },
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def user_edit_details(
    user_id: uuid.UUID,
    user: schemas.users.UserUpdate,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(deps.get_current_user),
):
    try:
        current_user_id = str(current_user.get('id'))
        if str(user_id) != current_user_id:
            raise HTTPException(
                status_code=403,
                detail='You can only edit your own profile',
            )

        db_user = await database.users.find_user_by_email(user.email) if user.email else None
        if user.email and db_user and str(db_user['id']) != current_user_id:
            raise HTTPException(
                status_code=403,
                detail='Email is already taken by another user',
            )

        user_data = user.model_dump(exclude_unset=True)
        if not user_data:
            raise HTTPException(
                status_code=400,
                detail='No fields to update',
            )

        updated_user = await database.users.edit_user(user_id, user_data)
        if not updated_user:
            raise HTTPException(
                status_code=404,
                detail='User not found',
            )

        await safe_cache_write(cache_user_after_write(r, updated_user))
        return updated_user
    except HTTPException:
        raise
    except IntegrityError:
        # Редкая гонка: email занят другим пользователем уже после pre-check.
        # Отдаём честный 409 вместо 500.
        logger.warning('Email uniqueness conflict on user %s edit', user_id)
        raise HTTPException(
            status_code=409,
            detail='Email is already taken by another user',
        )
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
