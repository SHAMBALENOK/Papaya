from flask import Flask, request, jsonify
import database.database as db
import uuid
from datetime import datetime, timezone, timedelta
app = Flask(__name__)

user_namespace = uuid.NAMESPACE_DNS

@app.route('/ping', methods=['GET'])
def send():
    return jsonify({"status": "ok"}), 200

@app.route('/auth/register', methods=['POST'])
def auth_reg():
    data = request.get_json()
    email = data.get('email', 'null')
    if email is None:
    password = data.get('password', 'null')
    fullname = data.get('fullName', 'null')
    id = str(uuid.uuid5(user_namespace, email))

    if email=='null' or password=='null' or fullname=='null':
        return jsonify({'status': 'invalidJSON'}), 400
    else:
        if db.find_user(id):
            return jsonify({'status': 'emailIsBusy',
                            'sex': db.find_user(id).email}), 409
        else:
            db.add_user(
                {
                    'user_id':id,
                    'email':email,
                    'password':password,
                    'fullname':fullname,
                    'region':region,
                    'gender':gender,
                    'age':age,
                    'MS':ms,
                    'role': 'USER'
                }
            )
            now = datetime.now(timezone.utc)
            formatted_time = now.isoformat().split('.')[0]+'Z'
            return jsonify({'accessToken': tokenz.generate_token(id, 'USER'),
                            'expiresIn': 3600,
                            'user':{
                                'id': id,
                                'email': email,
                                'fullName': fullname,
                                'age': age,
                                'region': region,
                                'gender': gender,
                                'maritalStatus': ms,
                                'role': 'USER',
                                'isActive': True,
                                'createdAt': formatted_time,
                                'updatedAt': formatted_time,
                            }
                            })



if __name__ == "__main__":
    app.run()
