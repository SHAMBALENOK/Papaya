import os
from json import JSONDecodeError
from flask import Flask, request, jsonify, redirect, url_for, render_template
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
# import database.database_users as db
# import database.database_events as db
import database.database as db
import middlewares.re_check as re_check
from werkzeug.security import check_password_hash
import uuid
from datetime import datetime, timezone
import logging
import sys


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

user_namespace = uuid.NAMESPACE_DNS
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

app.config['SERVER_NAME'] = os.getenv('SITE_NAME', 'localhost')
app.config['PREFERRED_URL_SCHEME'] = 'https'

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth'
login_manager.login_message = "Пожалуйста, войдите для доступа к этой странице"
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return db.find_user_by_id(user_id)

@app.route('/auth', methods=['GET'])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('main')) 
    return render_template('auth.html')


@app.route('/auth/register', methods=['POST'])
def register():
    try:
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        # user_ip = request.remote_addr
        email = data.get('email', 'null').strip()
        password = data.get('password', 'null')
        fullname = data.get('fullName', 'null').strip()
        check_fullname = re_check.is_valid_fullname(fullname)
        check_password = re_check.is_valid_password(password)
        if not re_check.is_valid_email(email):
            logger.debug(f"email {email} не прошел проверку", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Неверный email'}), 400
        if not check_fullname[0]:
            logger.debug(f"имя {fullname} не прошло проверку", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': check_fullname[1]}), 400
        if not check_password[0]:
            logger.debug(f"пароль {password} не прошел проверку", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': check_password[1]}), 400
        if db.find_user_by_email(email):
            logger.debug(f"пользователь уже есть в системе", exc_info=True)
            return jsonify({'status': 'emailIsBusy',
                            'hint': 'Email уже зарегистрирован'}), 409


        user_id = str(uuid.uuid5(user_namespace, email))
        db.add_user({
            'id': user_id,
            'email': email,
            'fullname': fullname,
            'password': password,
            'role': 'USER'

        })

        user = db.find_user_by_id(user_id)
        login_user(user, remember=True)

        logger.debug(f"Успешная регистрация {fullname} {email} под {user_id}, пароль {password}", exc_info=True)
        return jsonify({
            'status': 'Created',
            'redirect': url_for('main')
        }), 201

    except Exception as e:
        logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": "Ошибка сервера"
        }), 500


@app.route('/auth/login', methods=['POST'])
def login():
    try:
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        email = data.get('email', 'null').strip()
        password = data.get('password', 'null')
        # check_fullname = re_check.is_valid_fullname(fullname)
        check_password = re_check.is_valid_password(password)
        if not re_check.is_valid_email(email):
            logger.debug(f"email {email} не прошел проверку", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Неверный email'}), 400
        if not check_password[0]:
            logger.debug(f"пароль {password} не прошел проверку", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': check_password[1]}), 400

        db_user = db.find_user_by_email(email)

        if not db_user:
            logger.debug(f"такого пользователя нет", exc_info=True)
            return jsonify({'status': 'unauthorized',
                            'hint': f'email {email} не занят, используйте register'}), 401
        else:
            if not check_password_hash(db_user.password, password):
                logger.debug(f"пароль {password} или email {email} не прошел проверку", exc_info=True)
                return jsonify({'status': 'unauthorized',
                                'hint': f'Либо email {email} введен неправильно, либо - пароль'}), 401
            else:
                logger.debug(f"Успешный логин {email}, пароль {password}", exc_info=True)
                login_user(db_user, remember=True)
                return jsonify({
                    'status': 'success',
                    'redirect': url_for('main')
                }), 200

    except Exception as e:
        logger.error(f"Произошла ошибка при авторизации: {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": "Ошибка сервера"
        }), 500

@app.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        logger.debug(f"пользователь разлогинился", exc_info=True)
        return redirect(url_for('auth'))
    except Exception as e:
        logger.error(f"Произошла ошибка {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": "Ошибка сервера"
        }), 500


@app.route('/', methods=['GET'])
@login_required
def main():
    try:
        random_events = db.show_random_events(1)

        return render_template(
            'main.html',
            user_id=current_user.id,
            email=current_user.email,
            fullname=current_user.fullname,
            role=current_user.role,
            events=random_events
        )
    except Exception as e:
        logger.error(f"Произошла ошибка {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": "Ошибка сервера"
        }), 500

@app.route('/event/<event_id>', methods=['GET'])
@login_required
def event_details(event_id):

    event = db.find_event_by_id(event_id)

    if not event:
        logger.error(f"Произошла ошибка при воспроизведении события", exc_info=True)
        return jsonify({
            "status": "page_not_found",
            "hint": "страница не найдена"
        }), 404

    return render_template('event_detail.html', event=event)


if __name__ == '__main__':
  app.run(debug=True)