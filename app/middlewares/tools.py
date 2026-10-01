import bcrypt


def check_password(entered_password: str, stored_hash: bytes) -> bool:
    """
    Функция для проверки пароля

    Оборачивает ValueError bcrypt: пароль длиннее 72 байт (или битый хэш)
    не должен превращаться в 500, а просто считается неверным.
    """
    try:
        return bcrypt.checkpw(
            entered_password.encode('utf-8'),
            stored_hash.encode('utf-8'),
        )
    except ValueError:
        return False