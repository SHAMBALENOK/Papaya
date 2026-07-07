import uuid
from http.client import responses

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from json import JSONDecodeError
import app.middlewares.tools as tools
from app.database.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database

#TODO: добавить itsdangerous from starlette.middleware.sessions import SessionMiddleware (чек google ai)

USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication']
)

@tokenz.jwt_check
@auth_page.get('/',
               response_model=RedirectResponse,
               responses={
                   403: {'model': RedirectResponse, 'hint': 'вы уже зарегестрированы'}
               }
               )
async def auth(
        user: schemas.users.UserBase,
        jwt_response: bool = True,
):
    if jwt_response:
        return RedirectResponse(status_code=403, url='/')#TODO: сделать отображение html я тупой
    return RedirectResponse(status_code=200, url='/auth')

@auth_page.post('/register',
                response_model=RedirectResponse,
                responses={
                    400: {'model': HTTPException, 'hint': 'Неверный формат email или пароля'},
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
        if not re_check.is_valid_email(str(user.email)):
            raise HTTPException(status_code=400, detail='Неверный формат email')
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

        response = RedirectResponse(status_code=200, url='/',)#TODO: доделать response

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

        return jsonify({
            'status': 'Created',
            'redirect': url_for('main')#TODO: переделать
        }), 201
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Приложение сломалось c ошибкой\n{e}\n ¯\_(ツ)_/¯')



@auth_page.post('/login')
async def login():
    try:
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        email = data.get('email', 'null').strip()
        password = data.get('password', 'null')
        # check_fullname = re_check.is_valid_fullname(fullname)
        check_password = re_check.is_valid_password(password)
        if not re_check.is_valid_email(email):
            return jsonify({'status': 'badRequest',
                            'hint': 'Неверный email'}), 400
        if not check_password[0]:
            return jsonify({'status': 'badRequest',
                            'hint': check_password[1]}), 400

        db_user = db.find_user_by_email(email)

        if not db_user:
            return jsonify({'status': 'unauthorized',
                            'hint': f'email {email} не занят, используйте register'}), 401
        else:
            if not check_password_hash(db_user.password, password):
                return jsonify({'status': 'unauthorized',
                                'hint': f'Либо email {email} введен неправильно, либо - пароль'}), 401
            else:
                login_user(db_user, remember=True)
                return jsonify({
                    'status': 'success',
                    'redirect': url_for('main')
                }), 200

    except Exception as e:
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500

@tokenz.jwt_check
@auth_page.get('/logout')
async def logout(
        user: schemas.users.UserBase,
        jwt_response: bool = True,
):
    if jwt_response:
        #logout_user() TODO: сделать эту штуку
        return RedirectResponse('/auth')
    else:
        return {
            'response': 403,
            'hint': 'Вы не авторизованы',
        }
