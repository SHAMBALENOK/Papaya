from json import JSONDecodeError

import middlewares.tokenz as tokenz # Импортируем исправленный модуль
from functools import wraps
from flask import Flask, request, jsonify, redirect, url_for, render_template
from sqlalchemy.sql.coercions import expect

import database.database as db
import middlewares.re_check as re_check
import uuid
from werkzeug.security import check_password_hash
from datetime import datetime, timezone, timedelta

user_namespace = uuid.NAMESPACE_DNS
app = Flask(__name__)

def jwt_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'status': 'unauthorized', 'hint': 'Требуется авторизация'}), 401

        token = auth_header.split(' ')[1]

        try:
            payload = tokenz.decode_token(token)
            # Сохраняем payload для использования в обработчике
            request.current_user = payload
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'status': 'unauthorized', 'hint': str(e)}), 401

    return decorated_function

@app.route('/auth', methods=['GET'])
def auth():
    return render_template('auth.html')

@app.route('/auth/register', methods=['POST'])
def register():
    try:
        try:
            data = request.get_json()
        except JSONDecodeError:
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        # user_ip = request.remote_addr
        email = data.get('email', 'null').strip()
        password = data.get('password', 'null')
        fullname = data.get('fullName', 'null').strip()
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
            return jsonify({'status': 'emailIsBusy', 'hint': 'Email уже зарегистрирован'}), 409
        else:
            user_id = str(uuid.uuid5(user_namespace, email))
            db.add_user({
                'id': user_id,
                'email': email,
                'fullname': fullname,
                'password': password,
                'role': 'USER'

            })
            user_token = tokenz.generate_token(user_id, 'USER')
            now = datetime.now(timezone.utc)
            formatted_time = now.isoformat().split('.')[0] + 'Z'
            return jsonify({
                'status': 'Created',
                'token': user_token,
                'user': {
                        'id': user_id,
                        'email': email,
                        'fullName': fullname,
                        'role': 'USER',
                        'isActive': True,
                        'createdAt': formatted_time,
                        'updatedAt': formatted_time,
                },
            }), 201
    except Exception as e:
        print(e)
        return render_template('RottedPapaya.html')

@app.route('/auth/login', methods=['POST'])
def login():
    try:
        try:
            data = request.get_json()
        except JSONDecodeError:
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        email = data.get('email', 'null')
        password = data.get('password', 'null')
        # check_fullname = re_check.is_valid_fullname(fullname)
        check_password = re_check.is_valid_password(password)
        if not re_check.is_valid_email(email):
            return jsonify({'status': 'badRequest',
                            'hint': 'Неверный email'}), 400
        if not check_password[0]:
            return jsonify({'status': 'badRequest',
                            'hint': check_password[1]}), 400
        user_id = str(uuid.uuid5(user_namespace, email))
        db_user = db.find_user_by_email(email)

        if not db_user:
            return jsonify({'status': 'unauthorized',
                            'hint': f'email {email} не занят, используйте register'}), 401
        else:
            if check_password_hash(db_user.password, password) and email == db_user.email:
                user_token = tokenz.generate_token(db_user.id, db_user.role)
                return jsonify({
                    'status': 'success',
                    'user': {
                        'id': db_user.id,
                        'email': db_user.email,
                        'fullName': db_user.fullname,
                        'role': db_user.role,
                        'isActive': db_user.isActive
                    },
                    'token': user_token
                }), 200
            else:
                return jsonify({'status': 'unauthorized',
                                'hint': f'Либо email {email} введен неправильно, либо - пароль'}), 401
    except Exception as e:
        print(e)
        return jsonify({'status': 'internalError', 'hint': 'Ошибка сервера'}), 500

@app.route('/', methods=['GET'])
@jwt_required
def main():
    return render_template('auth.html')


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