from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse
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


@user_page.get('/users')
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}',
        )


@user_page.get(
    '/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'User not found'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    },
)
async def user_details(
    user_id: str,
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯',
        )


@user_page.post(
    '/{user_id}/edit_info',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Cannot find this user in database'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    },
)
async def user_edit_details(
    user_id: str,
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
                detail='It looks like you are trying to change not your profile',
            )

        db_user = await database.users.find_user_by_email(user.email)
        if not db_user:
            raise HTTPException(
                status_code=404,
                detail='Cannot find this user in database, try something else)',
            )
        if str(db_user['id']) != current_user_id:
            raise HTTPException(
                status_code=403,
                detail='It looks like you are trying to change not your profile',
            )

        user_data = {
            'name': user.name,
            'surname': user.surname,
            'gender': user.gender,
            'bday': user.bday,
            'bio': user.bio,
            'phone': user.phone,
            'country': user.country,
            'region': user.region,
            'status': user.status,
            'role': user.role,
        }
        clean_user = {
            key: value for key, value in user_data.items() if value is not None
        }
        updated_user = await database.users.edit_user(user_id, clean_user)
        if not updated_user:
            raise HTTPException(
                status_code=404,
                detail='Cannot find this user in database, try something else)',
            )

        await cache_user_after_write(r, updated_user)
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯',
        )