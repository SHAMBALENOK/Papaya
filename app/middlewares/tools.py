import bcrypt


#: Хэш-заглушка той же стоимости, что и реальные пароли (cost 12).
#:
#: Используется, когда пользователя с таким email нет: проверка пароля всё
#: равно выполняется, поэтому время ответа не зависит от существования
#: аккаунта. Иначе перебор email по времени ответа отличал бы существующий
#: адрес от несуществующего (user enumeration).
#:
#: Как и пароли в БД, заглушка хранится строкой: ``check_password`` кодирует
#: хэш в UTF-8. Байтовый хэш здесь ломал dummy-проверку (500 вместо 401).
_DUMMY_HASH = bcrypt.hashpw(
    b'papaya-dummy-password', bcrypt.gensalt(rounds=12)
).decode('utf-8')


def check_password(entered_password: str, stored_hash: str) -> bool:
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


def dummy_password_check(entered_password: str) -> bool:
    """Выполнить проверку пароля против заглушки и всегда вернуть False.

    Нужна, чтобы вход по несуществующему email занимал столько же времени,
    сколько вход по существующему с неверным паролем.
    """
    check_password(entered_password, _DUMMY_HASH)
    return False
