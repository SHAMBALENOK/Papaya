from json import JSONDecodeError

from flask import Flask, request, jsonify, redirect, url_for, render_template
from sqlalchemy.sql.coercions import expect

import database.database as db
import middlewares.re_check as re_check
import uuid
from datetime import datetime, timezone, timedelta

user_namespace = uuid.NAMESPACE_DNS
app = Flask(__name__)

@app.route('/', methods=['GET'])
def main():
    return redirect(url_for('auth'))

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
        email = data.get('email', 'null')
        password = data.get('password', 'null')
        fullname = data.get('fullName', 'null')
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
        id = str(uuid.uuid5(user_namespace, email))

        if db.find_user(id):
            return jsonify({'status': 'emailIsBusy',
                            'hint': f'email {db.find_user(id).email} занят, используйте login.'}), 409
        else:
            db.add_user({
                'id': id,
                'email': email,
                'fullname': fullname,
                'password': password,
                'role': 'USER'

            })
            now = datetime.now(timezone.utc)
            formatted_time = now.isoformat().split('.')[0] + 'Z'
            return jsonify({'user': {
                                'id': id,
                                'email': email,
                                'fullName': fullname,
                                'role': 'USER',
                                'isActive': True,
                                'createdAt': formatted_time,
                                'updatedAt': formatted_time,
                            }
                            })
    except Exception:
        return render_template('RottedPapaya.html')

@app.route('/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
    except JSONDecodeError:
        return jsonify({'status': 'badRequest',
                        'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
    email = data.get('email', 'null')
    password = data.get('password', 'null')
    fullname = data.get('fullName', 'null')
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
    id = str(uuid.uuid5(user_namespace, email))

    if not db.find_user(id):
        return jsonify({'status': 'emailIsNotBusy',
                        'hint': f'email {db.find_user(id).email} не занят, используйте register'}), 401
    

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