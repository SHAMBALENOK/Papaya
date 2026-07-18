import uuid
from fastapi import APIRouter, Depends, HTTPException, Cookie, Response
from fastapi.responses import JSONResponse
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database
from typing import Annotated

user_page = APIRouter(
    prefix='/user',
    tags=['users']
)

@user_page.get(
    '/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def user_details(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user = database.users.find_user_by_id(
            user_id=user_id,
            session=db,
            model=models.users,
        )
        if jwt_data.get('sub') == user.id:
            return user
        else:
            raise HTTPException(status_code=403, detail='It looks like you are trying to look on not your profile')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@user_page.post(
    '/{user_id}/edit_info',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'OK'},
        401: {'description': 'Access or refresh token missing'},
        403: {'description': 'Invalid refresh or access token'},
        404: {'description': 'Cannot find this user in database try something else)'},
        500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def user_edit_details(
        user_id: str,
        user: schemas.users.UserUpdate,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        db_user = await database.users.find_user_by_email(user.email, db, models.users)
        if not db_user:
            raise HTTPException(status_code=404, detail='Cannot find this user in database, try something else)')
        if db_user.id != jwt_data.get('sub'):
            raise HTTPException(status_code=403, detail='It looks like you are trying to change not your profile')#TODO: обнуление токена

        get_user = {
            'name': user.name,
            'surname': user.surname,
            'gender': user.gender,
            'bday': user.bday,
            'bio': user.bio,
            'phone': user.phone,
            'country': user.country,
            'region': user.region,
            'status': user.status,
            'role': user.role,
        }

        clean_user = {k: v for k, v in get_user.items() if v is not None}

        return database.users.edit_user(user_id, clean_user, db, models.users)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')