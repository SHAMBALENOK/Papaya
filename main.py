import os
from json import JSONDecodeError
from flask import Flask, flash, request, jsonify, redirect, url_for, render_template
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
# import database.database_users as db
# import database.database_events as db
import database.database as db
from middlewares.parse_tables import main as table_handling
from middlewares import tools as middletools
import middlewares.re_check as re_check
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime, timezone
import logging
import sys

from middlewares.tools import mkdir

UPLOAD_FOLDER = './tables'
ALLOWED_EXTENSIONS = {'pdf'}

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

# app.config['SERVER_NAME'] = os.getenv('SITE_NAME', 'localhost')
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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


        user_id = str(uuid.uuid5(user_namespace, email))
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
        logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
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
        logger.error(f"Произошла ошибка при авторизации: {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500

@app.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        return redirect(url_for('auth'))
    except Exception as e:
        logger.error(f"Произошла ошибка {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500


@app.route('/', methods=['GET'])
@login_required
def main():
    random_events = db.show_random_events(db.get_amount_of_events())

    return render_template(
        'main.html',
        user_id=current_user.id,
        email=current_user.email,
        fullname=current_user.fullname,
        role=current_user.role,
        events=random_events
    )

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

@app.route('/user/<user_id>', methods=['GET'])
@login_required
def user_details(user_id):
    user = db.find_user_by_id(user_id)
    if not user:
        logger.error(f"Произошла ошибка при воспроизведении информации о пользователе", exc_info=True)
        return jsonify({
            "status": "page_not_found",
            "hint": "страница не найдена"
        }), 404
    return render_template('user_detail.html', user=user)

@app.route('/user/<user_id>/edit_info', methods=['POST'])
@login_required
def user_edit_details(user_id):
    try:
        user = db.find_user_by_id(user_id)
        if not user:
            logger.error(f"Произошла ошибка при воспроизведении информации о пользователе", exc_info=True)
            return jsonify({
                "status": "page_not_found",
                "hint": "страница не найдена"
            }), 404
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        data = {
            'email': data.get('email', 'null').strip(),
            'password': data.get('password', 'null'),
            'fullname': data.get('fullName', 'null').strip(),
            'gender': data.get('gender', 'null'),
            'bday': data.get('bday', 'null'),
            'bio': data.get('bio', 'null'),
            'phone': data.get('phone', 'null'),
            'region': data.get('region', 'null'),
            'status': data.get('status', 'null'),
        }

        clean_data = {k: v for k, v in data.items() if v != 'null'}

        if not re_check.is_valid_email(clean_data['email']):
            return jsonify({'status': 'badRequest',
                            'hint': 'Неверный email'}), 400
        if not re_check.is_valid_fullname(clean_data['fullname'])[0]:
            return jsonify({'status': 'badRequest',
                            'hint': re_check.is_valid_fullname(clean_data['fullname'])[1]}), 400
        if not re_check.is_valid_password(clean_data['password'])[0]:
            return jsonify({'status': 'badRequest',
                            'hint': re_check.is_valid_password(clean_data['password'])[1]}), 400

        db.edit_user(user_id, clean_data)
        return jsonify({
            'status': 'success',
            'redirect': url_for('user_details', user_id=user_id)
        }), 200

    except Exception as e:
        logger.error(f"Произошла ошибка {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500

@app.route('/user/<user_id>/add_event', methods=['POST'])
@login_required
def add_event(user_id):
    try:
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400
        idd = str(uuid.uuid4())
        ins={
                'id': idd,
                'name': data.get('name', 'null').strip(),
                'place': data.get('place', 'null').strip(),
                'min_grade': data.get('min_grade', 'null'),
                'max_grade': data.get('max_grade', 'null'),
                'min_age': data.get('min_age', 'null'),
                'max_age': data.get('max_age', 'null'),
                'preview_picture': data.get('preview_picture', None),
                'picture': data.get('picture', None),

            }

        for key, value in ins.items():
            if key == 'name' and value == 'null':
                return jsonify({'status': 'badRequest',
                                'hint': f'Неверное {key}'}), 400

        db.add_event(ins)
        return jsonify({
            'status': 'success',
            'redirect': url_for('event_details', event_id=idd)
        }), 200

    except Exception as e:
        logger.error(f"Произошла ошибка {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500


@app.route('/user/<user_id>/<event_id>/edit_event', methods=['POST'])
@login_required
def event_edit_details(event_id, user_id):
    try:
        event = db.find_event_by_id(event_id)
        if not event:
            logger.error(f"Произошла ошибка при воспроизведении информации о событии", exc_info=True)
            return jsonify({
                "status": "page_not_found",
                "hint": "страница не найдена"
            }), 404
        try:
            data = request.get_json()
        except JSONDecodeError as e:
            logger.error(f"Произошла ошибка при регистрации: {e}", exc_info=True)
            return jsonify({'status': 'badRequest',
                            'hint': 'Некорректный JSON. Должно быть вы ставите специальные символы либо пытаетесь отправить некоррекный JSON на сервер.'}), 400

        data = {
            'name': data.get('name', 'null').strip(),
            'place': data.get('place', 'null').strip(),
            'min_grade': data.get('min_grade', 'null'),
            'max_grade': data.get('max_grade', 'null'),
            'min_age': data.get('min_age', 'null'),
            'max_age': data.get('max_age', 'null'),
            'preview_picture': data.get('preview_picture', 'null'),
            'picture': data.get('picture', 'null'),
        }

        clean_data = {k: v for k, v in data.items() if v != 'null'}

        db.edit_event(event_id, clean_data)
        return jsonify({
            'status': 'success',
            'redirect': url_for('event_details', event_id=event_id)
        }), 200

    except Exception as e:
        logger.error(f"Произошла ошибка {e}", exc_info=True)
        return jsonify({
            "status": "internal_error",
            "hint": f"Ошибка сервера {e}"
        }), 500

@app.route('/user/<user_id>/add_events_via_pdf_tables', methods=['POST'])
@login_required
def add_events_via_pdf_tables(user_id):
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file and middletools.allowed_file(file.filename, ALLOWED_EXTENSIONS):
        filename = secure_filename(file.filename)
        middletools.mkdir(f"{app.config['UPLOAD_FOLDER']}/{filename.split('.')[0]}")
        file.save(os.path.join(f"{app.config['UPLOAD_FOLDER']}/{filename.split('.')[0]}/{filename}"))
        table_handling.pdf_to_db(str(os.path.join(f"{app.config['UPLOAD_FOLDER']}/{filename.split('.')[0]}/{filename}")))
        return jsonify({
            'status': 'success',
            'redirect': url_for('user_details', user_id=user_id)
        }), 200

if __name__ == '__main__':
  app.run(debug=True)
