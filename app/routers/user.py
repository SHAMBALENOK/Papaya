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
import redis.asyncio as aioredis
from app.caching.main import get_redis

user_page = APIRouter(
    prefix='/user',
    tags=['users']
)

@user_page.get('/users')
async def users(
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

        if await r.get(f"user:{jwt_data.get('sub')}:users"):
            random_users = await database.users.show_random_users(
                quantity=await database.users.get_amount_of_users(session=db, model=models.users.Users),
                session=db,
                model=models.users.Users,
            )
            await r.set(f"user:{jwt_data.get('sub')}:users", random_users, ex=600)

            # Сериализуем users в словари
            users_list = [
                {
                    'id': str(ev.id),
                    'name': ev.name,
                    'surname': ev.surname,
                    'email': ev.email,
                    'gender': ev.disc,
                    'bday': ev.bday,
                    'bio': ev.bio,
                    'phone': ev.phone,
                    'country': ev.country,
                    'region': ev.region,
                    'status': ev.status,
                    'createdAt': ev.createdAt.isoformat() if ev.createdAt else None,
                    'updatedAt': ev.updatedAt.isoformat() if ev.updatedAt else None,
                }
                for ev in random_users
            ]
        else:
            users_list = r.get(f"user:{jwt_data.get('sub')}:users")

        return JSONResponse(status_code=200, content={
            'user_id': str(user_obj.id),       # UUID → str
            'user_name': user_obj.name,
            'user_surname': user_obj.surname,
            'user_email': user_obj.email,
            'user_role': user_obj.role,
            'users': users_list,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')

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
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if await r.get(f"user:{jwt_data.get('sub')}:object"):
            user_obj = await r.get(f"user:{jwt_data.get('sub')}:object")
        else:
            user_obj = await database.users.find_user_by_id(
                user_id=user_id,
                session=db,
                model=models.users.Users,
            )
            await r.set(f"user:{jwt_data.get('sub')}:object", user_obj, ex=600)

        return user_obj
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
        r: aioredis.Redis = Depends(get_redis),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        db_user = await database.users.find_user_by_email(user.email, db, models.users.Users)
        if not db_user:
            raise HTTPException(status_code=404, detail='Cannot find this user in database, try something else)')
        if str(db_user.id) != jwt_data.get('sub'):
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
        updated_user = await database.users.edit_user(user_id, clean_user, db, models.users.Users)

        await r.set(f"user:{jwt_data.get('sub')}:object", updated_user, ex=600)

        return updated_user

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')