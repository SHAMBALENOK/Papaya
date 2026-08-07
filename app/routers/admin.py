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


admin_page = APIRouter(
    prefix='/admin',
    tags=['administration']
)

# TODO Дашборд админов довести до ума по функционалу

# @admin_page.get('/',
#                 response_model=schemas.users.UserResponse,
#                 responses={
#                     200: {'description': 'OK'},
#                     403: {'description': 'Invalid refresh or access token or permission denied'},
#                     401: {'description': 'Access or refresh token missing'},
#                     500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
#                 }
#                 )
# async def auth(
#         db: AsyncSession = Depends(get_db),
#         access_jwt: Annotated[str | None, Cookie()] = None,
#         refresh_jwt: Annotated[str | None, Cookie()] = None,
# ):
#     try:
#         token = await tokenz.jwt_check(access_jwt, refresh_jwt)
#         user = await database.users.find_user_by_id(token['sub'], db, models.users.Users)
#         if user.role == "ADMIN":
#             return user
#         else:
#             raise HTTPException(status_code=403, detail=f'permission denied')
#
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@admin_page.get('/ban/{user_id}',
                response_model=schemas.users.UserResponse,
                responses={
                    200: {'description': 'OK'},
                    403: {'description': 'Invalid refresh or access token or permission denied'},
                    401: {'description': 'Access or refresh token missing'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def ban(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        token = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user = await database.users.find_user_by_id(token['sub'], db, models.users.Users)
        if user.role == "ADMIN":
            banned_user = await database.users.edit_user(
                user_id,
                {'isActive': False},
                db,
                models.users.Users
            )
            return banned_user
        else:
            raise HTTPException(status_code=403, detail=f'permission denied')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@admin_page.get('/archive_event/{event_id}',
                response_model=schemas.events.EventResponse,
                responses={
                    200: {'description': 'OK'},
                    403: {'description': 'Invalid refresh or access token or permission denied'},
                    401: {'description': 'Access or refresh token missing'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def archive_event(
        event_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        token = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user = await database.users.find_user_by_id(token['sub'], db, models.users.Users)
        if user.role == "ADMIN":
            archived_id = await database.events.edit_event(
                event_id,
                {'isActive': False},
                db,
                models.users.Users
            )
            return archived_id
        else:
            raise HTTPException(status_code=403, detail=f'permission denied')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@admin_page.get('/grant_admin/{user_id}',
                response_model=schemas.events.EventResponse,
                responses={
                    200: {'description': 'OK'},
                    403: {'description': 'Invalid refresh or access token or permission denied'},
                    401: {'description': 'Access or refresh token missing'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def grant_admin(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        token = await tokenz.jwt_check(access_jwt, refresh_jwt)
        from_user = await database.users.find_user_by_id(token['sub'], db, models.users.Users)
        if from_user.role == "ADMIN":
            to_user = await database.users.find_user_by_id(
                user_id,
                db,
                models.users.Users
            )
            if to_user.role == "ADMIN": raise HTTPException(status_code=403, detail=f'permission denied: you cannot grant ADMIN to ADMIN')
            granted_user = await database.users.edit_user(
                user_id,
                {'role': 'ADMIN'},
                db,
                models.users.Users
            )
            return granted_user
        else:
            raise HTTPException(status_code=403, detail=f'permission denied')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@admin_page.get('/demote_admin/{user_id}',
                response_model=schemas.events.EventResponse,
                responses={
                    200: {'description': 'OK'},
                    403: {'description': 'Invalid refresh or access token or permission denied'},
                    401: {'description': 'Access or refresh token missing'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def demote_admin(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        token = await tokenz.jwt_check(access_jwt, refresh_jwt)
        from_user = await database.users.find_user_by_id(token['sub'], db, models.users.Users)
        if from_user.role == "ADMIN":
            to_user = await database.users.find_user_by_id(
                user_id,
                db,
                models.users.Users
            )
            if to_user.role == "USER": raise HTTPException(status_code=403, detail=f'permission denied: you cannot demote USER to USER')
            demoted_user = await database.users.edit_user(
                user_id,
                {'role': 'USER'},
                db,
                models.users.Users
            )
            return demoted_user
        else:
            raise HTTPException(status_code=403, detail=f'permission denied')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')