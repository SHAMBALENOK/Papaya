import jwt
from datetime import datetime, timezone, timedelta
import os

SECRET = os.getenv('JWT_SECRET_KEY')
ALGORITHM = 'HS256'

def generate_token(user_id: str, role: str, expiration_hours: int = 24) -> str:
    """Генерация JWT токена с payload"""
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user_id,          # Subject (идентификатор пользователя)
        'role': role,            # Роль пользователя
        'iat': now,              # Время выдачи
        'exp': now + timedelta(hours=expiration_hours)  # Время истечения
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """
    Декодирование и валидация токена
    Возвращает payload или выбрасывает исключение
    """
    try:
        # Автоматическая проверка exp и iat
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Токен просрочен')
    except jwt.InvalidTokenError as e:
        raise ValueError(f'Неверный токен: {str(e)}')