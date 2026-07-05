import os

def mkdir(path: str) -> None:
    """
    Функция для создания папок, потому что мне лень писать все нижеуказанное
    """
    try:
        os.makedirs(path)
    except OSError:
        pass

def allowed_file(filename: str, extensions: list) -> bool:
    """
    Функция для проверки правильности расширения файла
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in extensions


def check_password(entered_password: str, stored_hash: bytes) -> bool:
    """
    Функция для проверки пароля
    """
    import bcrypt
    entered_bytes = entered_password.encode('utf-8')
    return bcrypt.checkpw(entered_bytes, stored_hash)