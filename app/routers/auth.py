import logging
import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import database, schemas
from app.caching.main import cache_user_after_write, get_cached_user, get_redis
from app.core.cache_guard import safe_cache_write
from app.core.config import COOKIE_SECURE
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
import app.middlewares.tools as tools


USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication'],
)

logger = logging.getLogger('papaya.auth')


def _set_auth_cookies(response: Response, access_jwt: str, refresh_jwt: str) -> None:
    """Записать JWT в HttpOnly-куки.

    ``secure=True`` ставится только в production (COOKIE_SECURE), чтобы локальная
    разработка по HTTP продолжала работать. ``SameSite=Lax`` отсекает
    state-changing cross-site запросы (базовая защита от CSRF) и не мешает
    обычной навигации SPA.
    """
    response.set_cookie(
        key='access_jwt',
        value=access_jwt,
        max_age=600,
        httponly=True,
        samesite='lax',
        secure=COOKIE_SECURE,
        path='/',
    )
    response.set_cookie(
        key='refresh_jwt',
        value=refresh_jwt,
        max_age=1209600,
        httponly=True,
        samesite='lax',
        secure=COOKIE_SECURE,
        path='/',
    )


def _clear_auth_cookies(response: Response) -> None:
    """Снять HttpOnly-куки при logout с теми же параметрами."""
    response.delete_cookie(
        'access_jwt',
        httponly=True,
        samesite='lax',
        secure=COOKIE_SECURE,
        path='/',
    )
    response.delete_cookie(
        'refresh_jwt',
        httponly=True,
        samesite='lax',
        secure=COOKIE_SECURE,
        path='/',
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
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        try:
            await tokenz.decode_access_token(access_jwt)
            # Access валиден — активная сессия, бутстрап по нему идёт сразу.
            return JSONResponse(status_code=403, content=None)
        except HTTPException as e:
            if e.status_code != 401:
                # Access не подписан/чужого типа — это уже не сессия клиента.
                return JSONResponse(status_code=200, content=None)
        # Access отсутствует или истёк — сессия жива, пока жив refresh;
        # новый access выдаст POST /auth/refresh по запросу.
        try:
            await tokenz.decode_refresh_token(refresh_jwt)
        except HTTPException:
            return JSONResponse(status_code=200, content=None)
        return JSONResponse(status_code=403, content=None)
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
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
        if user_data is None:
            raise HTTPException(status_code=409, detail='You already have account')
        await safe_cache_write(cache_user_after_write(r, user_data))

        _set_auth_cookies(
            response,
            access_jwt=await tokenz.create_access_token(
                ins={'sub': user_data['id']},
            ),
            refresh_jwt=await tokenz.create_refresh_token(
                ins={'sub': user_data['id']},
            ),
        )
        return user_data
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
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

        _set_auth_cookies(
            response,
            access_jwt=await tokenz.create_access_token(
                ins={'sub': db_user['id']},
            ),
            refresh_jwt=await tokenz.create_refresh_token(
                ins={'sub': db_user['id']},
            ),
        )

        # Заполняем новую версию через общий cache-aside helper. Пароль в Redis
        # не попадает, а конкурентное изменение профиля не может быть затёрто.
        await safe_cache_write(
            get_cached_user(
                r,
                str(db_user['id']),
                lambda: database.users.find_user_by_id(str(db_user['id'])),
            )
        )
        return db_user
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


@auth_page.post(
    '/logout',
    responses={
        200: {'description': 'Logged out successfully'},
        500: {'description': 'Internal server error'},
    },
)
async def logout():
    """Выход: снимаем HttpOnly-куки.

    JWT намеренно не валидируем: пользователь должен иметь возможность выйти,
    даже когда access и refresh уже истекли/невалидны (иначе сломанная сессия
    навсегда запирает в состоянии «залогинен» на фронтенде).
    """
    try:
        response = JSONResponse(status_code=200, content=None)
        _clear_auth_cookies(response)
        return response
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )


@auth_page.post(
    '/refresh',
    responses={
        200: {'description': 'New access token issued'},
        401: {'description': 'Refresh token missing or expired'},
        403: {'description': 'Invalid refresh token or account disabled'},
        500: {'description': 'Internal server error'},
    },
)
async def refresh(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Продление сессии: выдаёт новый access-токен по живому refresh.

    Refresh-токен НЕ ротируется (сохраняется прежним 14-дневный срок).
    Забаненный или удалённый пользователь access не получает.
    """
    try:
        claims = await tokenz.decode_refresh_token(refresh_jwt)
        user_id = claims.get('sub')
        user = await get_cached_user(
            r,
            str(user_id),
            lambda: database.users.find_user_by_id(str(user_id)),
        )
        if not user:
            raise HTTPException(
                status_code=401,
                detail={
                    'code': tokenz.REFRESH_TOKEN_INVALID,
                    'message': 'User not found',
                },
            )
        if user.get('isActive') is not True:
            raise tokenz.account_disabled_error()

        response = JSONResponse(status_code=200, content=None)
        response.set_cookie(
            key='access_jwt',
            value=await tokenz.create_access_token(ins={'sub': user_id}),
            max_age=600,
            httponly=True,
            samesite='lax',
            secure=COOKIE_SECURE,
            path='/',
        )
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
