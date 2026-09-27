"""Общие зависимости FastAPI: текущий пользователь и проверки прав.

Правила доступа Papaya собраны здесь, чтобы маршруты не повторяли одну и ту же
логику и чтобы модель прав была в одном месте:

- ``USER`` — посетитель: каталоги, поиск и страницы сущностей открыты;
- ``EDITOR`` — представитель университета: управляет связями **своего**
  университета с олимпиадами каталога; назначается только вместе с
  привязкой (см. ``app.database.users.apply_role``);
- ``ADMIN`` — администратор Papaya: каталог, импорт РСОШ, модерация. Права
  администратора не зависят от привязки к университету.

Роль всегда читается из актуальной версии пользователя (Redis-кэш с
версионированием или БД), а не из JWT: иначе понижение прав не действовало бы
до истечения токена.
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, HTTPException

from app import database
from app.caching.main import get_cached_user, get_redis
from app.database.users import ROLE_ADMIN, ROLE_UNIVERSITY_REP, ROLE_USER

import app.middlewares.tokenz.main as tokenz

__all__ = [
    'ROLE_ADMIN',
    'ROLE_UNIVERSITY_REP',
    'ROLE_USER',
    'can_manage_university',
    'get_current_user',
    'get_optional_user',
    'require_admin',
    'require_manage_university',
    'require_university_rep',
]


async def get_current_user(
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
) -> dict:
    """Текущий пользователь по JWT-cookie.

    Бросает 401 без токена и 404, если пользователь больше не существует
    (например, удалён администратором).
    """
    jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
    user_obj = await get_cached_user(
        r,
        str(jwt_data.get('sub')),
        lambda: database.users.find_user_by_id(jwt_data.get('sub')),
    )
    if not user_obj:
        raise HTTPException(status_code=404, detail='User not found')
    return user_obj


async def get_optional_user(
    r: aioredis.Redis = Depends(get_redis),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
) -> dict | None:
    """Текущий пользователь или None.

    Нужен публичным маршрутам, которые отдают гостю подтверждённые данные, а
    авторизованному пользователю — больше (например, собственные заявки вуза).
    Отсутствие токена здесь не ошибка.
    """
    try:
        return await get_current_user(r, access_jwt, refresh_jwt)
    except HTTPException:
        return None


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Только администратор Papaya."""
    if current_user.get('role') != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail='Permission denied')
    return current_user


async def require_university_rep(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Администратор или представитель университета.

    ``EDITOR`` без привязанного университета (``university_id`` пуст) — это
    противоречивое состояние, которого не должно быть: неизвестно, чьи именно
    связи ему позволено вести. Таких пользователей приводит в порядок
    администратор через ``POST /admin/role/{user_id}``, а до этого прав на
    управление связями у них нет.
    """
    role = current_user.get('role')
    if role == ROLE_ADMIN:
        return current_user
    if role == ROLE_UNIVERSITY_REP and current_user.get('university_id'):
        return current_user
    raise HTTPException(status_code=403, detail='Permission denied')


def can_manage_university(current_user: dict | None, university_id) -> bool:
    """Админ — любой университет; представитель — только свой."""
    if not current_user:
        return False
    if current_user.get('role') == ROLE_ADMIN:
        return True
    if current_user.get('role') != ROLE_UNIVERSITY_REP:
        return False
    own = current_user.get('university_id')
    return bool(own) and str(own) == str(university_id)


async def require_manage_university(
    university_id,
    current_user: dict = Depends(require_university_rep),
) -> dict:
    """Админ или представитель именно этого университета.

    Object-level проверка: представитель ИТМО не может управлять связями МФТИ,
    даже если знает его id.
    """
    if not can_manage_university(current_user, university_id):
        raise HTTPException(
            status_code=403,
            detail='You can only manage your own university',
        )
    return current_user


CurrentUser = Annotated[dict, Depends(get_current_user)]
OptionalUser = Annotated[dict | None, Depends(get_optional_user)]
AdminUser = Annotated[dict, Depends(require_admin)]
UniversityRep = Annotated[dict, Depends(require_university_rep)]
ManageUniversity = Annotated[dict, Depends(require_manage_university)]
