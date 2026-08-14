import uuid
from fastapi import APIRouter, Depends, HTTPException, Cookie, Response
from fastapi.responses import JSONResponse
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, database
from typing import Annotated
from app.caching.main import get_redis
import redis.asyncio as aioredis
import json

USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication']
)

@auth_page.get('/',
                responses={
                    200: {'description': 'OK'},
                    403: {'description': 'Invalid refresh or access token or you are already signed in'},
                    401: {'description': 'Access or refresh token missing'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def auth(
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        token = await tokenz.jwt_check(access_jwt, refresh_jwt)
        if token:
            raise HTTPException(status_code=403, detail="Already signed in")
    except HTTPException as e:
        if e.status_code == 401 or e.status_code == 403:
            return JSONResponse(status_code=200, content=None)
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@auth_page.post('/register',
                response_model=schemas.users.UserResponse,
                responses={
                    200: {'description': 'OK'},
                    400: {'description': 'incorrect password format'},
                    409: {'description': 'You already have account'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def register(
        response: Response,
        user: schemas.users.UserCreate,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
):
    try:
        check_password = re_check.is_valid_password(user.password)
        if not check_password[0]:
            raise HTTPException(status_code=400, detail=check_password[1])
        if await database.users.find_user_by_email(user.email):
            raise HTTPException(status_code=409, detail='You already have account')

        user_data = await database.users.add_user(
            ins={
                'name': user.name,
                'surname': user.surname,
                'email': user.email,
                'password': user.password
            },
        )
        await r.set(f"user:{user_data['id']}:object", json.dumps(user_data), ex=600)

        response.set_cookie(
            key="access_jwt",
            value=await tokenz.create_jwt(
                ins={
                    'sub': user_data['id']
                },
            ),
            max_age=600
        )
        response.set_cookie(
            key="refresh_jwt",
            value=await tokenz.create_jwt(
                ins={
                    'sub': user_data['id']
                },
                is_refresh=True
            ),
            max_age=1209600
        )

        return user_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')



@auth_page.post('/login',
                response_model=schemas.users.UserResponse,
                responses={
                    200: {'description': 'OK'},
                    404: {'description': 'your email is not in database, try to register'},
                    401: {'description': 'incorrect email or password'},
                    500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def login(
        response: Response,
        user: schemas.users.UserCreate,
        db: AsyncSession = Depends(get_db),
        r: aioredis.Redis = Depends(get_redis),
):
    try:
        db_user = await database.users.find_user_by_email(user.email)
        if not db_user:
            raise HTTPException(status_code=404, detail='your email is not in database, try to register')
        else:
            if not tools.check_password(user.password, db_user['password']):
                raise HTTPException(status_code=401, detail='incorrect email or password')
            else:
                response.set_cookie(
                    key="access_jwt",
                    value=await tokenz.create_jwt(
                        ins={
                            'sub': db_user['id']
                        },
                    ),
                    max_age=600
                )
                response.set_cookie(
                    key="refresh_jwt",
                    value=await tokenz.create_jwt(
                        ins={
                            'sub': db_user['id']
                        },
                        is_refresh=True
                    ),
                    max_age=1209600
                )
                cache_user = dict(db_user)
                cache_user.pop('password', None)
                await r.set(f"user:{db_user['id']}:object", json.dumps(cache_user), ex=600)
                return db_user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@auth_page.get('/logout',
               responses={
                   200: {'description': 'OK'},
                   403: {'description': 'Invalid refresh or access token or you are already signed in'},
                   401: {'description': 'Access or refresh token missing'},
                   500: {'description': 'Something has broken ¯\_(ツ)_/¯'},
               })
async def logout(
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
        r: aioredis.Redis = Depends(get_redis),
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        response = JSONResponse(status_code=200, content=None)
        response.delete_cookie('access_jwt')
        response.delete_cookie('refresh_jwt')
        await r.delete(f"user:{jwt_data.get('sub')}:object")
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')