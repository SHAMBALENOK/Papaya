import uuid
from http.client import responses

from fastapi import APIRouter, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database
from typing import Annotated


USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication']
)

auth_page.get('/',
                response_model=JSONResponse,
                responses={
                    403: {'model': HTTPException, 'hint': 'Invalid refresh or access token or you are already signed in'},
                    401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
                    500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@auth_page.post('/register',
                response_model=JSONResponse,
                responses={
                    200: {'model': JSONResponse, 'hint': 'OK'},
                    400: {'model': HTTPException, 'hint': 'incorrect password format'},
                    409: {'model': HTTPException, 'hint': 'You already have account'},
                    500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def register(
        user: schemas.users.UserCreate,
        db: AsyncSession = Depends(get_db)
):
    try:
        check_password = re_check.is_valid_password(user.password)
        if not check_password[0]:
            raise HTTPException(status_code=400, detail=check_password[1])
        if await database.users.find_user_by_email(user.email, db, models.users):
            raise HTTPException(status_code=409, detail='You already have account')

        user_data = await database.users.add_user(
            ins={
                'name': user.name,
                'surname': user.surname,
                'email': user.email,
                'password': user.password
            },
            session=db,
            model=models.users,
        )

        response = JSONResponse(status_code=200, content=user_data)
        response.set_cookie(
            key="access_jwt",
            value=await tokenz.create_jwt(
                ins={
                    'sub': user_data.id
                },
            ),
            max_age=600
        )
        response.set_cookie(
            key="refresh_jwt",
            value=await tokenz.create_jwt(
                ins={
                    'sub': user_data.id
                },
                is_refresh=True
            ),
            max_age=1209600
        )

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')



@auth_page.post('/login',
                response_model=JSONResponse,
                responses={
                    200: {'model': JSONResponse, 'hint': 'OK'},
                    404: {'model': HTTPException, 'hint': 'your email is not in database, try to register'},
                    401: {'model': HTTPException, 'hint': 'incorrect email or password'},
                    500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
                }
                )
async def login(
        user: schemas.users.UserCreate,
        db: AsyncSession = Depends(get_db)
):
    try:
        db_user = await database.users.find_user_by_email(user.email, db, models.users)
        if not db_user:
            raise HTTPException(status_code=404, detail='your email is not in database, try to register')
        else:
            if not tools.check_password(user.password, db_user.password):
                raise HTTPException(status_code=401, detail='incorrect email or password')
            else:
                response = JSONResponse(status_code=200, content=db_user)
                response.set_cookie(
                    key="access_jwt",
                    value=await tokenz.create_jwt(
                        ins={
                            'sub': db_user.id
                        },
                    ),
                    max_age=600
                )
                response.set_cookie(
                    key="refresh_jwt",
                    value=await tokenz.create_jwt(
                        ins={
                            'sub': db_user.id
                        },
                        is_refresh=True
                    ),
                    max_age=1209600
                )
                return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')

@auth_page.get('/logout',
               response_model=JSONResponse,
               responses={
                   200: {'model': JSONResponse, 'hint': 'OK'},
                   403: {'model': HTTPException, 'hint': 'Invalid refresh or access token or you are already signed in'},
                   401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
                   500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
               })
async def logout(
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        await tokenz.jwt_check(access_jwt, refresh_jwt)
        response = JSONResponse(status_code=200, content=None)
        response.delete_cookie('access_jwt')
        response.delete_cookie('refresh_jwt')
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯')
