import uuid
from fastapi import APIRouter, Depends, HTTPException, Cookie, Response
from fastapi.responses import JSONResponse
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, database
from app.middlewares.task_queue import run_task
from typing import Annotated
import redis.asyncio as aioredis
from app.caching.main import get_redis
import json

user_page = APIRouter(
    prefix='/user',
    tags=['users']
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

        # --- текущий пользователь: кэш или БД ---
        user_cache_key = f"user:{sub}:object"
        cached_user = await r.get(user_cache_key)
        if cached_user:
            user_obj = json.loads(cached_user)
        else:
            user_obj = await run_task(database.users.find_user_by_id, sub)
            if not user_obj:
                raise HTTPException(status_code=404, detail='User not found')
            await r.set(user_cache_key, json.dumps(user_obj), ex=600)

        # --- список пользователей: кэш или БД ---
        users_cache_key = f"user:{sub}:users"
        cached_users = await r.get(users_cache_key)
        if cached_users:
            users_list = json.loads(cached_users)
        else:
            quantity = await run_task(database.users.get_amount_of_users)
            users_list = await run_task(database.users.show_random_users, quantity)
            await r.set(users_cache_key, json.dumps(users_list), ex=600)

        return JSONResponse(status_code=200, content={
            'user_id': str(user_obj['id']),       # UUID → str
            'user_name': user_obj['name'],
            'user_surname': user_obj['surname'],
            'user_email': user_obj['email'],
            'user_role': user_obj['role'],
            'users': users_list,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')

@user_page.get(
    '/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def user_details(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        # Кэш по ключу запрашиваемого пользователя, а не текущего (sub)
        cache_key = f"user:{user_id}:object"
        cached = await r.get(cache_key)
        if cached:
            user_obj = json.loads(cached)
        else:
            user_obj = await run_task(database.users.find_user_by_id, user_id)
            if not user_obj:
                raise HTTPException(status_code=404, detail='User not found')
            await r.set(cache_key, json.dumps(user_obj), ex=600)

        return user_obj
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@user_page.post(
    '/{user_id}/edit_info',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Cannot find this user in database try something else)'},
        500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
    }
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
        db_user = await run_task(database.users.find_user_by_email, user.email)
        if not db_user:
            raise HTTPException(status_code=404, detail='Cannot find this user in database, try something else)')
        if db_user['id'] != jwt_data.get('sub'):
            raise HTTPException(status_code=403, detail='It looks like you are trying to change not your profile')#TODO: обнуление токена

        get_user = {
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

        clean_user = {k: v for k, v in get_user.items() if v is not None}
        updated_user = await run_task(database.users.edit_user, user_id, clean_user)
        if not updated_user:
            raise HTTPException(status_code=404, detail='Cannot find this user in database, try something else)')

        await r.set(f"user:{jwt_data.get('sub')}:object", json.dumps(updated_user), ex=600)

        return updated_user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')