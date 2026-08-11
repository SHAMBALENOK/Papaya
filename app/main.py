from fastapi import FastAPI, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database
from typing import Annotated
from app.routers import user, events, auth, admin
import os
from app.database.database import db_lifespan
from app.caching.main import redis_lifespan, get_redis
from contextlib import asynccontextmanager
import redis.asyncio as aioredis

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


@app.get('/api/v1/')
async def main(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if await r.get(f"user:{jwt_data.get('sub')}:object"):
            user_obj = await r.get(f"user:{jwt_data.get('sub')}:object")
        else:
            user_obj = await database.users.find_user_by_id(jwt_data.get('sub'), db, models.users.Users)
            await r.set(f"user:{jwt_data.get('sub')}:object", user_obj, ex=600)

        return JSONResponse(status_code=200, content={
            'user_id': str(user_obj.id),       # UUID → str
            'user_name': user_obj.name,
            'user_surname': user_obj.surname,
            'user_email': user_obj.email,
            'user_role': user_obj.role,
        })
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
        try:
            jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
            if await r.get(f"user:{jwt_data.get('sub')}:object"):
                user_obj = await r.get(f"user:{jwt_data.get('sub')}:object")
            else:
                user_obj = await database.users.find_user_by_id(jwt_data.get('sub'), db, models.users.Users)
                await r.set(f"user:{jwt_data.get('sub')}:object", user_obj, ex=600)

            return JSONResponse(status_code=200, content={
                'user_id': str(user_obj.id),  # UUID → str
                'user_name': user_obj.name,
                'user_surname': user_obj.surname,
            })
        except HTTPException:
            return JSONResponse(status_code=200)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')

# --- Frontend ---
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

app.mount('/frontend', StaticFiles(directory=FRONTEND_DIR), name='frontend')


@app.get('/')
@app.get('/{path:path}')
async def spa_fallback(path: str = ''):
    # Если запрашивается файл из /frontend — отдаём его
    file_path = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(FRONTEND_DIR, 'index.html'))