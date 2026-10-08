import logging
import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import database, schemas
from app.caching.main import cache_user_after_write, get_cached_user, get_redis
from app.core import deps
from app.core.cache_guard import safe_cache_write
from app.core.config import COOKIE_SECURE
from app.core.deps import ACCOUNT_BLOCKED_DETAIL
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
        403: {'description': 'Already signed in or invalid token'},
        500: {'description': 'Internal server error'},
    },
)
async def auth(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Проверка «есть ли активная сессия».

    Использует общий механизм ``get_current_user``: сессия есть только если
    пользователь существует и не заблокирован. Заблокированный с валидной
    кукой — «не вошёшь» (200), иначе фронтенд показывал бы экран
    «уже залогинен» аккаунту, который не может выполнить ни одного
    авторизованного действия.
    """
    try:
        await deps.get_current_user(r, access_jwt, refresh_jwt)
    except HTTPException as exc:
        # Нет токена либо пользователь удалён/заблокирован — не вошли.
        if exc.status_code in (401, 404):
            return JSONResponse(status_code=200, content=None)
        if exc.status_code == 403 and exc.detail == ACCOUNT_BLOCKED_DETAIL:
            return JSONResponse(status_code=200, content=None)
        if exc.status_code == 403:
            # Невалидный токен — как и раньше, ошибка, а не «не вошли».
            raise
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
    raise HTTPException(status_code=403, detail='Already signed in')


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
            access_jwt=await tokenz.create_jwt(ins={'sub': user_data['id']}),
            refresh_jwt=await tokenz.create_jwt(
                ins={'sub': user_data['id']},
                is_refresh=True,
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
        403: {'description': 'Account is blocked'},
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
        # Блокировка проверяется после пароля: неверный пароль остаётся 401 и
        # не превращается в подтверждение существования заблокированного
        # аккаунта. С правильным паролем залогиниться всё равно нельзя.
        if db_user.get('isActive') is False:
            raise HTTPException(status_code=403, detail=ACCOUNT_BLOCKED_DETAIL)

        _set_auth_cookies(
            response,
            access_jwt=await tokenz.create_jwt(ins={'sub': db_user['id']}),
            refresh_jwt=await tokenz.create_jwt(
                ins={'sub': db_user['id']},
                is_refresh=True,
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
        _clear_auth_cookies(response)
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(
            status_code=500,
            detail='Internal server error',
        )
