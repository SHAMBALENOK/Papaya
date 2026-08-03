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
import uuid as uuid_mod

events_page = APIRouter(
    prefix='/events',
    tags=['events']
)

UPLOAD_FOLDER = '../tables'

@events_page.post(
    '/add_event',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def add_event(
        event: schemas.events.EventCreate,  # ← только один body параметр
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        # TODO: проверка прав
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_id = jwt_data.get('sub')

        db_event = await database.events.add_event(
            ins={
                'owner': user_id,
                'name': event.name,
                'disc': event.disc,
                'preview_picture': event.preview_picture,
                'picture': event.picture,
            },
            session=db,
            model=models.events.Events,
        )
        return db_event

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@events_page.post(
    '/edit_event',
    response_model=schemas.events.EventResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Event not found'},
        500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def event_edit_details(
        event: schemas.events.EventCreate,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None
):
    try:
        #TODO: проверка прав
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        db_event = await database.events.find_event_by_id(
            event_id=str(event.id),
            session=db,
            model=models.events.Events
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

        up_event = await database.events.edit_event(
            event_id=str(event.id),
            ins=clean_data,
            session=db,
            model=models.events.Events
        )
        return up_event


    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@events_page.post(
    '/add_events_via_pdf_tables',
    response_model=list[schemas.events.EventResponse],  # ← список событий
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\\_(ツ)_/¯'},
    }
)
async def add_events_via_pdf_tables(
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_id = jwt_data.get('sub')
        filename = secure_filename(file.filename)
        tools.mkdir(f"{UPLOAD_FOLDER}/{filename.split('.')[0]}")
        file_location = f"{UPLOAD_FOLDER}/{filename.split('.')[0]}/{filename}"
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)

        created = await table_handling.main.pdf_to_db(
            file_location, db, user_id
        )
        return created
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯'
        )