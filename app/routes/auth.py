import uuid
from app import models as db
from fastapi import APIRouter
from json import JSONDecodeError
import app.middlewares.tools as tools
from app.databse.database import get_db
import app.middlewares.re_check as re_check
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession

USER_NAMESPACE = uuid.NAMESPACE_DNS

auth_page = APIRouter(
    prefix='/auth',
    tags=['authentication']
)

@tokenz.jwt_check
@auth_page.get('/')
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('main'))
    return render_template('auth.html')

@auth_page.post('/register')
def register():
    try:
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        # user_ip = request.remote_addr
        email = data.get('email', 'null').strip()
        password = data.get('password', 'null')
        fullname = data.get('fullName', 'null').strip()
        gender = data.get('gender', 'null')
        bday = data.get('bday', 'null')
        bio = data.get('bio', 'null')
        phone = data.get('phone', 'null')
        region = data.get('region', 'null')
        status = data.get('status', 'null')
        check_fullname = re_check.is_valid_fullname(fullname)
        check_password = re_check.is_valid_password(password)
        if not re_check.is_valid_email(email):
            return jsonify({'status': 'badRequest',
                            'hint': 'Неверный email'}), 400
        if not check_fullname[0]:
            return jsonify({'status': 'badRequest',
                            'hint': check_fullname[1]}), 400
        if not check_password[0]:
            return jsonify({'status': 'badRequest',
                            'hint': check_password[1]}), 400
        if db.find_user_by_email(email):
            return jsonify({'status': 'emailIsBusy',
                            'hint': 'Email уже зарегистрирован'}), 409


        user_id = str(uuid.uuid5(USER_NAMESPACE, email))
        db.add_user({
            'id': user_id,
            'email': email,
            'fullname': fullname,
            'password': password,
            'role': 'USER',
            'gender': gender,
            'bday': bday,
            'bio': bio,
            'phone': phone,
            'region': region,
            'status': status,

        })

        user = db.find_user_by_id(user_id)
        login_user(user, remember=True)

        return jsonify({
            'status': 'Created',
            'redirect': url_for('main')
        }), 201

    except Exception as e:
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500


@auth_page.post('/login')
def login():
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

@auth_page.get('/logout')
def logout():
    try:
        logout_user()
        return redirect(url_for('auth'))
    except Exception as e:
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500

