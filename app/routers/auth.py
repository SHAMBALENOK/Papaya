import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import database, schemas
from app.caching.main import cache_user_after_write, get_cached_user, get_redis
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
import app.middlewares.tools as tools


USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication'],
)


@auth_page.get(
    '/',
    responses={
        200: {'description': 'OK — not signed in'},
        403: {'description': 'Already signed in'},
        500: {'description': 'Internal server error'},
    },
)
async def auth(
    db: AsyncSession = Depends(get_db),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        token = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if token:
            raise HTTPException(status_code=403, detail='Already signed in')
        return JSONResponse(status_code=200, content=None)
    except HTTPException as e:
        if e.status_code == 401:
            return JSONResponse(status_code=200, content=None)
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Internal server error: {e}',
        )


@auth_page.post(
    '/register',
    response_model=schemas.users.UserResponse,
    status_code=201,
    responses={
        201: {'description': 'User created successfully'},
        400: {'description': 'Incorrect password format'},
        409: {'description': 'Account already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def register(
    response: Response,
    user: schemas.users.UserCreate,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    try:
        check_password = re_check.is_valid_password(user.password)
        if not check_password[0]:
            raise HTTPException(status_code=400, detail=check_password[1])
        if await database.users.find_user_by_email(user.email):
            raise HTTPException(status_code=409, detail='You already have account')

        user_data = await database.users.add_user(
            ins={
                'name': user.name,
                'surname': user.surname,
                'email': user.email,
                'password': user.password,
            },
        )
        await cache_user_after_write(r, user_data)

        response.set_cookie(
            key='access_jwt',
            value=await tokenz.create_jwt(ins={'sub': user_data['id']}),
            max_age=600,
        )
        response.set_cookie(
            key='refresh_jwt',
            value=await tokenz.create_jwt(
                ins={'sub': user_data['id']},
                is_refresh=True,
            ),
            max_age=1209600,
        )
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Internal server error: {e}',
        )


@auth_page.post(
    '/login',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Login successful'},
        401: {'description': 'Invalid email or password'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def login(
    response: Response,
    user: schemas.users.LoginRequest,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    try:
        db_user = await database.users.find_user_by_email(user.email)
        if not db_user:
            raise HTTPException(
                status_code=401,
                detail='Invalid email or password',
            )
        if not tools.check_password(user.password, db_user['password']):
            raise HTTPException(
                status_code=401,
                detail='Invalid email or password',
            )

        response.set_cookie(
            key='access_jwt',
            value=await tokenz.create_jwt(ins={'sub': db_user['id']}),
            max_age=600,
        )
        response.set_cookie(
            key='refresh_jwt',
            value=await tokenz.create_jwt(
                ins={'sub': db_user['id']},
                is_refresh=True,
            ),
            max_age=1209600,
        )

        # Заполняем новую версию через общий cache-aside helper. Пароль в Redis
        # не попадает, а конкурентное изменение профиля не может быть затёрто.
        await get_cached_user(
            r,
            str(db_user['id']),
            lambda: database.users.find_user_by_id(str(db_user['id'])),
        )
        return db_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Internal server error: {e}',
        )


@auth_page.post(
    '/logout',
    responses={
        200: {'description': 'Logged out successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        500: {'description': 'Internal server error'},
    },
)
async def logout(
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        await tokenz.jwt_check(access_jwt, refresh_jwt)
        response = JSONResponse(status_code=200, content=None)
        response.delete_cookie('access_jwt')
        response.delete_cookie('refresh_jwt')
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Internal server error: {e}',
        )
