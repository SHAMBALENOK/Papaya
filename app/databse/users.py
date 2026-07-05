import bcrypt
from datetime import datetime, timezone
from typing import Any, Callable, ParamSpec, TypeVar, Coroutine

session_Spec = ParamSpec('session_Spec')
user_Return = TypeVar('user_Return')


def add_user(ins: dict, session: session_Spec, model: Callable) -> user_Return:
    """
    Функция для создания пользователя в базе данных
    """
    salt = bcrypt.gensalt(rounds=12)
    user = model(
        name=ins.get('name'),
        surname=ins.get('surname'),
        email=ins.get('email'),
        password=bcrypt.hashpw(ins.get('password').encode('utf-8'), salt),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def find_user_by_email(email: str, session: session_Spec, model: Callable) -> user_Return:
    """
    Функция для поиска пользователя по email
    """
    return session.query(model).filter(model.email == email).first()


def find_user_by_id(user_id: str, session: session_Spec, model: Callable) -> user_Return:
    """
    Функция для поиска пользователя по id
    """
    return session.query(model).filter(model.id == user_id).first()


def edit_user(user_id: str, ins: dict, session: session_Spec, model: Callable) -> user_Return:
    """
    Функция редактирования данных
    """
    now = datetime.now(timezone.utc)
    user = session.query(model).filter(model.id == user_id).first()
    for key, value in ins.items():
        setattr(user, key, value)
    user.updatedAt = now
    session.commit()
    session.refresh(user)
    return user
