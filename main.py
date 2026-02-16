import os
from json import JSONDecodeError
from flask import Flask, request, jsonify, redirect, url_for, render_template
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import database.database as db
import middlewares.re_check as re_check
from werkzeug.security import check_password_hash
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
import logging
load_dotenv()

user_namespace = uuid.NAMESPACE_DNS
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

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
            if not check_password_hash(db_user.password, password) and email != db_user.email:
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
        logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": "Ошибка сервера"
        }), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    logger.debug(f"пользователь разлогинился", exc_info=True)
    return redirect(url_for('auth'))


@app.route('/', methods=['GET'])
@login_required
def main():
    logger.debug(f"пользователь посетил основную страничку", exc_info=True)
    return render_template(
        'main.html',
        user_id=current_user.id,
        email=current_user.email,
        fullname=current_user.fullname,
        role=current_user.role
    )


# return jsonify({
    #     "box_1": {
    #       "image": image1,
    #       "content": content1,
    #       "URL": URL1,
    #     },
    #     "box_2": {
    #       "image": image2,
    #       "content": content2,
    #       "URL": URL2,
    #     },
    #     "box_3": {
    #       "image": image3,
    #       "content": content3,
    #       "URL": URL3,
    #     },
    #     "box_4": {
    #       "image": image4,
    #       "content": content4,
    #       "URL": URL4,
    #     },
    #     "box_5": {
    #       "image": image5,
    #       "content": content5,
    #       "URL": URL5,
    #     },
    #     "box_6": {
    #       "image": image6,
    #       "content": content6,
    #       "URL": URL6,
    #     },
    #     "box_7": {
    #       "image": image7,
    #       "content": content7,
    #       "URL": URL7,
    #     },
    #     "box_8": {
    #       "image": image8,
    #       "content": content8,
    #       "URL": URL8,
    #     },
    #     "box_9": {
    #       "image": image9,
    #       "content": content9,
    #       "URL": URL9,
    #     },
    #     "box_10": {
    #       "image": image10,
    #       "content": content10,
    #       "URL": URL10,
    #     },
    # }), 200

if __name__ == '__main__':
  app.run(debug=True)