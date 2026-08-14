from fastapi import APIRouter, Depends, HTTPException, Cookie, File, UploadFile, Response
from fastapi.responses import JSONResponse
from werkzeug.utils import secure_filename
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz
import app.middlewares.parse_tables as table_handling
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, database
from app.middlewares.task_queue import run_task
from typing import Annotated
import os
import shutil
import uuid as uuid_mod
import redis.asyncio as aioredis
from app.caching.main import get_redis
import json

events_page = APIRouter(
    prefix='/events',
    tags=['events']
)

# Каталог загрузок: в Docker задаётся TABLES_DIR=/app/app/tables
UPLOAD_FOLDER = os.getenv(
    'TABLES_DIR',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tables')),
)


async def _get_cached_user(sub: str, db: AsyncSession, r: aioredis.Redis) -> dict:
    """
    Возвращает пользователя из кэша или БД в виде dict.
    При промахе кэша результат сериализуется и кладётся в кэш.
    """
    cache_key = f"user:{sub}:object"
    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)
    user_obj = await database.users.find_user_by_id(sub)
    if not user_obj:
        raise HTTPException(status_code=404, detail='User not found')
    await r.set(cache_key, json.dumps(user_obj), ex=600)
    return user_obj


async def _get_authorized_user(sub: str, db: AsyncSession, r: aioredis.Redis) -> dict:
    """
    Возвращает пользователя (кэш или БД) и проверяет права EDITOR/ADMIN.
    """
    user_obj = await _get_cached_user(sub, db, r)
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
    }
)
async def add_event(
        event: schemas.events.EventCreate,  # ← только один body параметр
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        await _get_authorized_user(jwt_data.get('sub'), db, r)  # Проверка прав

        db_event = await database.events.add_event(
            ins={
                'owner': jwt_data.get('sub'),
                'name': event.name,
                'disc': event.disc,
                'preview_picture': event.preview_picture,
                'picture': event.picture,
            },
        )
        await r.set(f"event:{db_event['id']}", json.dumps(db_event), ex=600)
        return db_event

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯')

@events_page.post(
    '/edit_event/{event_id}',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Event not found'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    }
)
async def event_edit_details(
        event_id: str,
        event: schemas.events.EventCreate,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        await _get_authorized_user(jwt_data.get('sub'), db, r)  # Проверка прав

        # Проверяем, что событие существует (кэш или БД)
        cache_key = f"event:{event_id}"
        cached = await r.get(cache_key)
        if cached:
            db_event = json.loads(cached)
        else:
            db_event = await database.events.find_event_by_id(event_id)
            if not db_event:
                raise HTTPException(status_code=404, detail='Event not found')
            await r.set(cache_key, json.dumps(db_event), ex=600)

        data = {
            'owner': event.owner,
            'name': event.name,
            'disc': event.disc,
            'preview_picture': event.preview_picture,
            'picture': event.picture,
        }

        clean_data = {k: v for k, v in data.items() if v != 'null'}

        up_event = await database.events.edit_event(event_id=event_id, ins=clean_data)
        if not up_event:
            raise HTTPException(status_code=404, detail='Event not found')
        await r.set(cache_key, json.dumps(up_event), ex=600)
        return up_event

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯')

@events_page.post(
    '/add_events_via_tables',
    response_model=list[schemas.events.EventResponse],  # ← список событий
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    }
)
async def add_events_via_tables(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    file: UploadFile = File(...),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_id = jwt_data.get('sub')
        await _get_authorized_user(user_id, db, r)  # Проверка прав

        tables_cache_key = f"user:{user_id}:tables"
        cached = await r.get(tables_cache_key)
        if cached:
            created = json.loads(cached)
        else:
            filename = secure_filename(file.filename)
            tools.mkdir(f"{UPLOAD_FOLDER}/{filename.split('.')[0]}")
            file_location = f"{UPLOAD_FOLDER}/{filename.split('.')[0]}/{filename}"
            with open(file_location, "wb+") as file_object:
                shutil.copyfileobj(file.file, file_object)

            if filename.split('.')[-1] == 'pdf':
                created = await table_handling.main.pdf_to_db(
                    file_location, user_id
                )
            elif filename.split('.')[-1] == 'xlsx':
                created = await run_task(table_handling.sql_processing.tabulate, file_location, user_id)
            else:
                raise HTTPException(status_code=400, detail='Unsupported file format')
            await r.set(tables_cache_key, json.dumps(created), ex=120)
        return created
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯'
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
        user_obj = await _get_cached_user(sub, db, r)

        events_cache_key = f"user:{sub}:events"
        cached = await r.get(events_cache_key)
        if cached:
            events_list = json.loads(cached)
        else:
            quantity = await database.events.get_amount_of_events()
            events_list = await database.events.show_random_events(quantity)
            await r.set(events_cache_key, json.dumps(events_list), ex=600)
        return JSONResponse(status_code=200, content={
            'user_id': str(user_obj['id']),       # UUID → str
            'user_name': user_obj['name'],
            'user_surname': user_obj['surname'],
            'user_email': user_obj['email'],
            'user_role': user_obj['role'],
            'events': events_list,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')

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
        user_obj = await _get_cached_user(sub, db, r)

        my_events_cache_key = f"user:{sub}:my_events"
        cached_events = await r.get(my_events_cache_key)
        if cached_events:
            my_events = json.loads(cached_events)
        else:
            quantity = await database.events.get_amount_of_events()
            events_list = await database.events.show_random_events(quantity)

            my_events = []
            for event in events_list:
                if event['owner'] == sub:
                    my_events.append(event)

            await r.set(my_events_cache_key, json.dumps(my_events), ex=600)

        return JSONResponse(status_code=200, content={
            'user_id': str(user_obj['id']),       # UUID → str
            'user_name': user_obj['name'],
            'user_surname': user_obj['surname'],
            'user_email': user_obj['email'],
            'user_role': user_obj['role'],
            'events': my_events,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')

@events_page.get(
    '/{event_id}',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Page is missing'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    }
)
async def event_details(
        event_id: uuid_mod.UUID,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        cache_key = f"event:{event_id}"
        cached = await r.get(cache_key)
        if cached:
            event = json.loads(cached)
        else:
            event = await database.events.find_event_by_id(str(event_id))
            if not event: raise HTTPException(status_code=404, detail='Page is missing')
            await r.set(cache_key, json.dumps(event), ex=600)

        return event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯')