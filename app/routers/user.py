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
    cache_user_after_write,
    get_cached_user,
    get_cached_users,
    get_redis,
)
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz


user_page = APIRouter(
    prefix='/user',
    tags=['users'],
)

logger = logging.getLogger('papaya.user')


class UserListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    surname: str | None = None
    email: str | None = None
    gender: str | None = None
    bday: str | None = None
    bio: str | None = None
    phone: str | None = None
    country: str | None = None
    region: str | None = None
    status: str | None = None
    role: str | None = None
    isActive: bool | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class UsersListResponse(BaseModel):
    user_id: str | None = None
    user_name: str | None = None
    user_surname: str | None = None
    user_email: str | None = None
    user_role: str | None = None
    users: List[UserListItem]


@user_page.get(
    '/users',
    response_model=UsersListResponse,
    responses={
        200: {'description': 'Current user info and list of active users'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def users(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        sub = jwt_data.get('sub')
        user_obj = await get_cached_user(
            r,
            sub,
            lambda: database.users.find_user_by_id(sub),
        )
        if not user_obj:
            raise HTTPException(status_code=404, detail='User not found')

        users_list = await get_cached_users(
            r,
            False,
            lambda: database.users.list_users(include_inactive=False),
        )
        return JSONResponse(
            status_code=200,
            content={
                'user_id': str(user_obj['id']),
                'user_name': user_obj['name'],
                'user_surname': user_obj['surname'],
                'user_email': user_obj['email'],
                'user_role': user_obj['role'],
                'users': users_list,
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


@user_page.get(
    '/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User profile'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def user_details(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        await tokenz.jwt_check(access_jwt, refresh_jwt)
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
        403: {'description': 'Cannot edit other user\'s profile'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def user_edit_details(
    user_id: uuid.UUID,
    user: schemas.users.UserUpdate,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        current_user_id = str(jwt_data.get('sub'))
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

        await cache_user_after_write(r, updated_user)
        return updated_user
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
