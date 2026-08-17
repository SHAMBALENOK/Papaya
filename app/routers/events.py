import os
import shutil
import uuid as uuid_mod
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from werkzeug.utils import secure_filename

from app import database, schemas
from app.caching.main import (
    cache_event_after_write,
    cache_events_after_write,
    get_cached_event,
    get_cached_events,
    get_cached_user,
    get_redis,
)
from app.database.database import get_db
import app.middlewares.parse_tables as table_handling
import app.middlewares.tokenz.main as tokenz


events_page = APIRouter(
    prefix='/events',
    tags=['events'],
)

# Каталог загрузок: в Docker задаётся TABLES_DIR=/app/app/tables.
UPLOAD_FOLDER = os.getenv(
    'TABLES_DIR',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tables')),
)
_ALLOWED_TABLE_EXTENSIONS = {'.pdf', '.xlsx'}


async def _get_cached_user(sub: str, r: aioredis.Redis) -> dict:
    """Получить актуального пользователя из версионного кэша или БД."""
    user_obj = await get_cached_user(
        r,
        sub,
        lambda: database.users.find_user_by_id(sub),
    )
    if not user_obj:
        raise HTTPException(status_code=404, detail='User not found')
    return user_obj


async def _get_authorized_user(sub: str, r: aioredis.Redis) -> dict:
    """Проверить права на создание и изменение событий."""
    user_obj = await _get_cached_user(sub, r)
    if user_obj.get('role') not in ('EDITOR', 'ADMIN'):
        raise HTTPException(status_code=403, detail='Permission denied')
    return user_obj


@events_page.post(
    '/add_event',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    },
)
async def add_event(
    event: schemas.events.EventCreate,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_id = jwt_data.get('sub')
        await _get_authorized_user(user_id, r)

        db_event = await database.events.add_event(
            ins={
                'owner': user_id,
                'name': event.name,
                'disc': event.disc,
                'preview_picture': event.preview_picture,
                'picture': event.picture,
            },
        )
        await cache_event_after_write(r, db_event)
        return db_event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯',
        )


@events_page.post(
    '/edit_event/{event_id}',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Event not found'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    },
)
async def event_edit_details(
    event_id: str,
    event: schemas.events.EventCreate,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        await _get_authorized_user(jwt_data.get('sub'), r)

        db_event = await get_cached_event(
            r,
            event_id,
            lambda: database.events.find_event_by_id(event_id),
        )
        if not db_event:
            raise HTTPException(status_code=404, detail='Event not found')

        data = {
            'owner': event.owner,
            'name': event.name,
            'disc': event.disc,
            'preview_picture': event.preview_picture,
            'picture': event.picture,
        }
        clean_data = {key: value for key, value in data.items() if value != 'null'}

        updated_event = await database.events.edit_event(
            event_id=event_id,
            ins=clean_data,
        )
        if not updated_event:
            raise HTTPException(status_code=404, detail='Event not found')
        await cache_event_after_write(r, updated_event)
        return updated_event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯',
        )


@events_page.post(
    '/add_events_via_tables',
    response_model=list[schemas.events.EventResponse],
    responses={
        200: {'description': 'OK'},
        400: {'description': 'Unsupported file format'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    },
)
async def add_events_via_tables(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    file: UploadFile = File(...),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_id = jwt_data.get('sub')
        await _get_authorized_user(user_id, r)

        filename = secure_filename(file.filename or '')
        extension = os.path.splitext(filename)[1].lower()
        if not filename or extension not in _ALLOWED_TABLE_EXTENSIONS:
            raise HTTPException(status_code=400, detail='Unsupported file format')

        # У каждого импорта свой каталог. Результат POST-запроса намеренно не
        # кэшируется: повторная загрузка обязана создать события из нового файла.
        upload_dir = os.path.join(UPLOAD_FOLDER, uuid_mod.uuid4().hex)
        os.makedirs(upload_dir, exist_ok=False)
        file_location = os.path.join(upload_dir, filename)
        try:
            with open(file_location, 'wb') as file_object:
                shutil.copyfileobj(file.file, file_object)
        finally:
            await file.close()

        if extension == '.pdf':
            created = await table_handling.main.pdf_to_db(file_location, user_id)
        else:
            # XLSX обрабатывается напрямую: здесь нет Celery-задачи, а значит
            # нет worker time limit и синхронного ожидания AsyncResult.
            created = await table_handling.sql_processing.tabulate(
                file_location,
                user_id,
            )

        await cache_events_after_write(r, created)
        return created
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯',
        )


@events_page.get('/dashboard')
async def event_dashboard(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        sub = jwt_data.get('sub')
        user_obj = await _get_cached_user(sub, r)
        events_list = await get_cached_events(
            r,
            'active',
            lambda: database.events.list_events(active_only=True),
        )
        return JSONResponse(
            status_code=200,
            content={
                'user_id': str(user_obj['id']),
                'user_name': user_obj['name'],
                'user_surname': user_obj['surname'],
                'user_email': user_obj['email'],
                'user_role': user_obj['role'],
                'events': events_list,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}',
        )


@events_page.get('/dashboard/my_events')
async def my_event_dashboard(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        sub = jwt_data.get('sub')
        user_obj = await _get_cached_user(sub, r)
        my_events = await get_cached_events(
            r,
            f'owner:{sub}',
            lambda: database.events.list_events(active_only=False, owner=sub),
        )
        return JSONResponse(
            status_code=200,
            content={
                'user_id': str(user_obj['id']),
                'user_name': user_obj['name'],
                'user_surname': user_obj['surname'],
                'user_email': user_obj['email'],
                'user_role': user_obj['role'],
                'events': my_events,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}',
        )


@events_page.get(
    '/{event_id}',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Page is missing'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    },
)
async def event_details(
    event_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        await tokenz.jwt_check(access_jwt, refresh_jwt)
        event_id_string = str(event_id)
        event = await get_cached_event(
            r,
            event_id_string,
            lambda: database.events.find_event_by_id(event_id_string),
        )
        if not event:
            raise HTTPException(status_code=404, detail='Page is missing')
        return event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯',
        )