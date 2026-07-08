import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database

USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication']
)

@tokenz.jwt_check
@auth_page.get('/',
               response_model=JSONResponse,
               responses={
                   200: {'model': JSONResponse, 'hint': 'OK'},
                   403: {'model': HTTPException, 'hint': 'Вы уже зарегестрированы'}
               }
               )
async def auth(
        user: schemas.users.UserBase,
        jwt_response: bool = True,
):
    if jwt_response:
        raise HTTPException(
            status_code=403,
            detail="Вы уже зарегистрированы",
            headers={"location": "/"}
        )
    return JSONResponse(status_code=200, content=None)

@auth_page.post('/register',
                response_model=JSONResponse,
                responses={
                    200: {'model': JSONResponse, 'hint': 'OK'},
                    400: {'model': HTTPException, 'hint': 'Неверный формат пароля'},
                    409: {'model': HTTPException, 'hint': 'email уже зарегистрирован'},
                    500: {'model': HTTPException, 'hint': 'Приложение сломалось ¯\_(ツ)_/¯'}
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
            raise HTTPException(status_code=409, detail='email уже зарегистрирован')

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
            key="access_jwt",
            value=await tokenz.create_jwt(
                ins={
                    'sub': user_data.id
                },
            ),
            max_age=1209600
        )

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Приложение сломалось c ошибкой\n{e}\n ¯\_(ツ)_/¯')



@auth_page.post('/login',
                response_model=JSONResponse,
                responses={
                    200: {'model': JSONResponse, 'hint': 'OK'},
                    404: {'model': HTTPException, 'hint': 'email не зарегистрирован, зарегистрируйтесь'},
                    401: {'model': HTTPException, 'hint': 'неверный email или пароль'},
                    500: {'model': HTTPException, 'hint': 'Приложение сломалось ¯\_(ツ)_/¯'}
                }
                )
async def login(
        user: schemas.users.UserCreate,
        db: AsyncSession = Depends(get_db)
):
    try:
        db_user = await database.users.find_user_by_email(user.email, db, models.users)
        if not db_user:
            raise HTTPException(status_code=404, detail='email не зарегистрирован, зарегистрируйтесь')
        else:
            if not tools.check_password(user.password, db_user.password):
                raise HTTPException(status_code=401, detail='неверный email или пароль')
            else:
                return JSONResponse(status_code=200, content={"location": "/"})


    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Приложение сломалось c ошибкой\n{e}\n ¯\_(ツ)_/¯')

@tokenz.jwt_check
@auth_page.get('/logout',
               response_model=JSONResponse,
               responses={
                   200: {'model': JSONResponse, 'hint': 'OK'},
                   403: {'model': JSONResponse, 'hint': 'Unauthorized'},
               })
async def logout(
        user: schemas.users.UserBase,
        jwt_response: bool = True,
):
    if jwt_response:
        return JSONResponse(status_code=200, content={"location": "/auth"})
    else:
        return JSONResponse(status_code=403, content={"location": "/auth"})
