from fastapi import FastAPI, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import database
from typing import Annotated
from app.routers import user, events, auth, admin
import os
from app.database.database import db_lifespan
from app.caching.main import redis_lifespan, get_redis
from contextlib import asynccontextmanager
import redis.asyncio as aioredis
import json


@asynccontextmanager
async def main_lifespan(app: FastAPI):
    async with db_lifespan(app):
        async with redis_lifespan(app):
            yield


app = FastAPI(lifespan=main_lifespan)

app.include_router(user.user_page, prefix="/api/v1")
app.include_router(events.events_page, prefix="/api/v1")
app.include_router(auth.auth_page, prefix="/api/v1")
app.include_router(admin.admin_page, prefix="/api/v1")


async def get_user_from_cache_or_db(
        user_id: str,
        r: aioredis.Redis,
        db: AsyncSession
) -> dict:
    """Получить пользователя из кэша или БД"""
    cache_key = f"user:{user_id}:object"
    cached_user = await r.get(cache_key)

    if cached_user:
        return json.loads(cached_user)

    user_obj = await database.users.find_user_by_id(user_id)
    if user_obj:
        await r.set(cache_key, json.dumps(user_obj), ex=600)
        return user_obj

    return None


@app.get('/api/v1/')
async def main(
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_dict = await get_user_from_cache_or_db(jwt_data.get('sub'), r, db)

        if not user_dict:
            raise HTTPException(status_code=404, detail="User not found")

        return JSONResponse(status_code=200, content=user_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@app.get('/api/v1/welcome')
async def welcome(
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_dict = await get_user_from_cache_or_db(jwt_data.get('sub'), r, db)

        if not user_dict:
            return JSONResponse(status_code=200, content={})

        return JSONResponse(status_code=200, content={
            'user_id': user_dict.get('id'),
            'user_name': user_dict.get('name'),
            'user_surname': user_dict.get('surname'),
        })
    except HTTPException:
        return JSONResponse(status_code=200, content={})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


# --- Frontend ---
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
        headers={"Cache-Control": "no-store, max-age=0"},
    )