import os
from contextlib import asynccontextmanager
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.caching.main import get_cached_user, get_redis, redis_lifespan
from app.database.database import db_lifespan, get_db
import app.middlewares.tokenz.main as tokenz
from app.routers import admin, auth, events, user


@asynccontextmanager
async def main_lifespan(app: FastAPI):
    async with db_lifespan(app):
        async with redis_lifespan(app):
            yield


app = FastAPI(lifespan=main_lifespan)

app.include_router(user.user_page, prefix='/api/v1')
app.include_router(events.events_page, prefix='/api/v1')
app.include_router(auth.auth_page, prefix='/api/v1')
app.include_router(admin.admin_page, prefix='/api/v1')


async def get_user_from_cache_or_db(
    user_id: str,
    r: aioredis.Redis,
    db: AsyncSession,
) -> dict | None:
    """Получить актуальную версию пользователя из Redis или БД."""
    return await get_cached_user(
        r,
        user_id,
        lambda: database.users.find_user_by_id(user_id),
    )


@app.get('/api/v1/')
async def main(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_dict = await get_user_from_cache_or_db(
            jwt_data.get('sub'),
            r,
            db,
        )
        if not user_dict:
            raise HTTPException(status_code=404, detail='User not found')
        return JSONResponse(status_code=200, content=user_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}',
        )


@app.get('/api/v1/welcome')
async def welcome(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_dict = await get_user_from_cache_or_db(
            jwt_data.get('sub'),
            r,
            db,
        )
        if not user_dict:
            return JSONResponse(status_code=200, content={})
        return JSONResponse(
            status_code=200,
            content={
                'user_id': user_dict.get('id'),
                'user_name': user_dict.get('name'),
                'user_surname': user_dict.get('surname'),
            },
        )
    except HTTPException:
        return JSONResponse(status_code=200, content={})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}',
        )


FRONTEND_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'frontend'))
INDEX_FILE = os.path.join(FRONTEND_DIR, 'index.html')

app.mount('/frontend', StaticFiles(directory=FRONTEND_DIR), name='frontend')


@app.get('/')
@app.get('/{path:path}')
async def spa_fallback(path: str = ''):
    """Отдать файл фронтенда или точку входа SPA для клиентского маршрута."""
    if path:
        file_path = os.path.realpath(os.path.join(FRONTEND_DIR, path))
        if (
            os.path.commonpath((FRONTEND_DIR, file_path)) == FRONTEND_DIR
            and os.path.isfile(file_path)
        ):
            return FileResponse(file_path)

    return FileResponse(
        INDEX_FILE,
        headers={'Cache-Control': 'no-store, max-age=0'},
    )