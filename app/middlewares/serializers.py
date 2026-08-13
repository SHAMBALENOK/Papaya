"""
Сериализация ORM-объектов в словари для хранения в Redis-кэше.

Redis умеет хранить только bytes/str/int/float, поэтому складывать
SQLAlchemy-объекты напрямую нельзя (иначе:
"Invalid input of type: 'Users'. Convert to a bytes, string, int or float first.").
Вместо этого объекты превращаются в JSON-совместимые словари.
"""
from typing import Any, Optional


def _iso(value: Any) -> Optional[str]:
    """datetime -> ISO-строка, None -> None"""
    return value.isoformat() if value else None


def user_to_dict(user) -> dict:
    """
    Users (ORM) -> dict для кэша.

    Пароль в кэш не попадает: он нигде не читается из кэша,
    а хранить хэш пароля лишний раз не стоит.
    """
    return {
        'id': str(user.id),
        'email': user.email,
        'name': user.name,
        'surname': user.surname,
        'gender': user.gender,
        'bday': user.bday,
        'bio': user.bio,
        'phone': user.phone,
        'country': user.country,
        'region': user.region,
        'status': user.status,
        'role': user.role,
        'isActive': user.isActive,
        'createdAt': _iso(user.createdAt),
        'updatedAt': _iso(user.updatedAt),
    }


def event_to_dict(event) -> dict:
    """Events (ORM) -> dict для кэша."""
    return {
        'id': str(event.id),
        'owner': str(event.owner) if event.owner else None,
        'name': event.name,
        'disc': event.disc,
        'preview_picture': event.preview_picture,
        'picture': event.picture,
        'isActive': event.isActive,
        'createdAt': _iso(event.createdAt),
        'updatedAt': _iso(event.updatedAt),
    }