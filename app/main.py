import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import validate_config
from app.core.errors import install_exception_handlers

validate_config()
from app import schemas
from app.caching.main import redis_lifespan
from app.core import deps
from app.database.database import db_lifespan
from app.routers import (
    admin,
    auth,
    docs,
    health,
    imports,
    olympiads,
    search,
    universities,
    user,
)


logger = logging.getLogger('papaya.main')


@asynccontextmanager
async def main_lifespan(app: FastAPI):
    async with db_lifespan(app):
        async with redis_lifespan(app):
            yield


app = FastAPI(lifespan=main_lifespan)

install_exception_handlers(app)

app.include_router(user.user_page, prefix='/api/v1')
app.include_router(auth.auth_page, prefix='/api/v1')
app.include_router(universities.universities_page, prefix='/api/v1')
app.include_router(olympiads.olympiads_page, prefix='/api/v1')
app.include_router(docs.docs_page, prefix='/api/v1')
app.include_router(imports.imports_page, prefix='/api/v1')
app.include_router(search.search_page, prefix='/api/v1')
app.include_router(admin.admin_page, prefix='/api/v1')
app.include_router(health.health_page)


@app.get(
    '/api/v1/',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Current user profile'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token or account is blocked'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def main(current_user: dict = Depends(deps.get_current_user)):
    """Профиль текущего пользователя.

    Авторизация через общий механизм ``get_current_user``: единая проверка
    токена и блокировки аккаунта вместо собственного ``jwt_check``. Словарь
    возвращается как есть — ``response_model`` отфильтрует его по контракту
    ``UserResponse``.
    """
    return current_user


FRONTEND_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'frontend'))
INDEX_FILE = os.path.join(FRONTEND_DIR, 'index.html')

app.mount('/frontend', StaticFiles(directory=FRONTEND_DIR), name='frontend')


@app.get('/')
@app.get('/{path:path}')
async def spa_fallback(path: str = ''):
    """Отдать файл фронтенда или точку входа SPA для клиентского маршрута.

    Несуществующие пути под ``/api/v1/`` возвращают JSON 404, а не HTML: иначе
    опечатка в URL API тихо превращается в 200 с index.html и клиент не может
    отличить «роут не найден» от успешного ответа.
    """
    if path.startswith('api/'):
        raise HTTPException(status_code=404, detail='Not found')

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