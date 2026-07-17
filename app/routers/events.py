from fastapi import APIRouter, Depends, HTTPException, Cookie, File, UploadFile, Response
from fastapi.responses import JSONResponse
from werkzeug.utils import secure_filename
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz
import app.middlewares.parse_tables as table_handling
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database
from typing import Annotated
import shutil

events_page = APIRouter(
    prefix='/event',
    tags=['events']
)

UPLOAD_FOLDER = '../tables'

@events_page.get(
    '/{event_id}',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'model': schemas.events.EventResponse, 'hint': 'OK'},
        401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
        403: {'model': HTTPException, 'hint': 'Invalid refresh or access token'},
        404: {'model': HTTPException, 'hint': 'Page is missing'},
        500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def event_details(
        event_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        event = database.events.find_event_by_id(
            event_id=event_id,
            session=db,
            model=models.events,
        )
        if not event: raise HTTPException(status_code=404, detail='Page is missing')

        return event
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@events_page.post(
    '/add_event',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'model': schemas.events.EventResponse, 'hint': 'OK'},
        401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
        403: {'model': HTTPException, 'hint': 'Invalid refresh or access token'},
        500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def add_event(
        user: schemas.users.UserBase,
        event: schemas.events.EventCreate,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        #TODO: проверка прав
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if jwt_data.get('sub') != user.id:
            raise HTTPException(status_code=403)  # TODO: обнуление токена
        db_event = database.events.add_event(
            ins={
                    'owner': event.owner,
                    'name': event.name,
                    'disc': event.disc,
                    'preview_picture': event.preview_picture,
                    'picture': event.picture,
                },
            session=db,
            model=models.events,
        )
        return db_event

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@events_page.post(
    '/edit_event',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'model': schemas.events.EventResponse, 'hint': 'OK'},
        401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
        403: {'model': HTTPException, 'hint': 'Invalid refresh or access token'},
        404: {'model': HTTPException, 'hint': 'Event not found'},
        500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def event_edit_details(
        user: schemas.users.UserBase,
        event: schemas.events.EventCreate,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None
):
    try:
        #TODO: проверка прав
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if jwt_data.get('sub') != user.id:
            raise HTTPException(status_code=403)  # TODO: обнуление токена
        db_event = database.events.find_event_by_id(
            event_id=event.id,
            session=db,
            model=models.events
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

        clean_data = {k: v for k, v in data.items() if v != 'null'}

        up_event = database.events.edit_event(
            event_id=event.id,
            ins=clean_data,
            session=db,
            model=models.events
        )
        return up_event


    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@events_page.post(
    '/add_events_via_pdf_tables',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'model': schemas.users.UserResponse, 'hint': 'OK'},
        401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
        403: {'model': HTTPException, 'hint': 'Invalid refresh or access token'},
        500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def add_events_via_pdf_tables(
    user: schemas.users.UserBase,
    event: schemas.events.EventCreate,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if jwt_data.get('sub') != user.id:
            raise HTTPException(status_code=403, detail='It looks like you are trying to use not your profile')  # TODO: обнуление токена

        filename = secure_filename(file.filename)
        tools.mkdir(f"{UPLOAD_FOLDER}/{filename.split('.')[0]}")
        file_location = f"{UPLOAD_FOLDER}/{filename.split('.')[0]}/{filename}"
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)

        table_handling.main.pdf_to_db(f"{UPLOAD_FOLDER}/{filename.split('.')[0]}/{filename}", db)

        return user

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')