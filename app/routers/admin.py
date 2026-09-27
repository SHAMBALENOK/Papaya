"""Администрирование Papaya.

Администратор отвечает за каталог и его наполнение:

- пользователи: блокировка, роли, привязка представителя к университету;
- олимпиады: архивирование/возврат из архива, ручное создание и правка;
- заявки БВИ: подтверждение и снятие связей университет ↔ олимпиада.

Все маршруты требуют роль ``ADMIN``: проверка общая и живёт в
``app.core.deps.require_admin``.
"""

import logging
import uuid
from typing import List

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError

from app import database, schemas
from app.caching.main import cache_user_after_write, get_redis
from app.core import deps
from app.core.cache_guard import safe_cache_write
from app.database import users as users_db
from app.rsosh.persist import ARCHIVE_BY_RSOSH, ARCHIVE_MANUAL

admin_page = APIRouter(
    prefix='/admin',
    tags=['administration'],
)

logger = logging.getLogger('papaya.admin')


class AdminUserListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    surname: str | None = None
    email: str | None = None
    role: str | None = None
    university_id: str | None = None
    isActive: bool | None = None
    createdAt: str | None = None


class AdminUsersResponse(BaseModel):
    users: List[AdminUserListItem]


class AdminOlympiadListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    source_doc_id: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class AdminOlympiadsResponse(BaseModel):
    olympiads: List[AdminOlympiadListItem]


class AdminBviListItem(BaseModel):
    id: str | None = None
    university_id: str | None = None
    university_name: str | None = None
    olympiad_id: str | None = None
    olympiad_name: str | None = None
    status: str | None = None
    createdAt: str | None = None


class AdminBviResponse(BaseModel):
    links: List[AdminBviListItem]


class UniversityAssignment(BaseModel):
    """Привязка пользователя к университету (роль представителя).

    Пустой ``university_id`` отвязывает представителя от университета.
    """

    university_id: str | None = None


class RoleAssignment(BaseModel):
    """Назначение роли пользователю.

    Единый контракт управления ролью: роль и привязка меняются вместе, поэтому
    нельзя получить ``EDITOR`` без университета или привязать университет
    обычному пользователю.

    - ``USER`` — обычный школьник, ``university_id`` должен быть пуст;
    - ``EDITOR`` — представитель университета, ``university_id`` обязателен;
    - ``ADMIN`` — администратор Papaya; привязка не влияет на его права, но
      сохраняется, чтобы понижение вернуло роль представителя.
    """

    role: str
    university_id: str | None = None

    @field_validator('role')
    @classmethod
    def _check_role(cls, v):
        if v not in users_db.ROLES:
            raise ValueError('role must be one of ' + ', '.join(users_db.ROLES))
        return v


def _serialize_user(user: dict) -> dict:
    return {
        'id': user.get('id'),
        'name': user.get('name'),
        'surname': user.get('surname'),
        'email': user.get('email'),
        'role': user.get('role'),
        'university_id': user.get('university_id'),
        'isActive': user.get('isActive'),
        'createdAt': user.get('createdAt'),
    }


@admin_page.get(
    '/users',
    response_model=AdminUsersResponse,
    responses={
        200: {'description': 'List of all users including inactive'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_users(current_user: deps.AdminUser = None):
    """Все пользователи, включая заблокированных."""
    try:
        users = await database.users.list_users(include_inactive=True)
        return JSONResponse(
            status_code=200,
            content={'users': [_serialize_user(user) for user in users]},
        )
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.get(
    '/olympiads',
    response_model=AdminOlympiadsResponse,
    responses={
        200: {'description': 'Полный каталог олимпиад, включая архивные'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_olympiads(current_user: deps.AdminUser = None):
    """Каталог олимпиад включая архивные (вне актуального перечня РСОШ)."""
    try:
        olympiads = await database.olympiads.list_olympiads(status=None)
        return {
            'olympiads': [
                {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'status': item.get('status'),
                    'source_doc_id': item.get('source_doc_id'),
                    'createdAt': item.get('createdAt'),
                    'updatedAt': item.get('updatedAt'),
                }
                for item in olympiads
            ],
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.get(
    '/bvi',
    response_model=AdminBviResponse,
    responses={
        200: {'description': 'Заявки и подтверждённые связи БВИ'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_bvi_links(
    status: str | None = None,
    current_user: deps.AdminUser = None,
):
    """Очередь модерации: заявки университетов на связи БВИ."""
    try:
        links = await database.bvi.list_links(status=status)
        enriched: list[dict] = []
        for link in links:
            university = await database.universities.get_university(
                link['university_id']
            )
            olympiad = await database.olympiads.get_olympiad(link['olympiad_id'])
            enriched.append(
                {
                    'id': link.get('id'),
                    'university_id': link.get('university_id'),
                    'university_name': (university or {}).get('name'),
                    'olympiad_id': link.get('olympiad_id'),
                    'olympiad_name': (olympiad or {}).get('name'),
                    'status': link.get('status'),
                    'createdAt': link.get('createdAt'),
                }
            )
        return {'links': enriched}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _change_user(
    user_id: uuid.UUID,
    ins: dict,
    r: aioredis.Redis,
) -> dict:
    """Изменить пользователя и сбросить версионный кэш ролей.

    Роль читается через versioned-кэш Redis, поэтому после записи кэш обязан
    быть инвалидирован — иначе понижение прав не действует до истечения JWT.
    """
    updated = await database.users.edit_user(user_id, ins)
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    await safe_cache_write(cache_user_after_write(r, updated))
    return updated


@admin_page.post(
    '/ban/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User banned successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def ban(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Заблокировать пользователя (isActive = False)."""
    try:
        return await _change_user(user_id, {'isActive': False}, r)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/unban/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User unbanned successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        500: {'description': 'Internal server error'},
    },
)
async def unban(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Разблокировать пользователя (isActive = True)."""
    try:
        return await _change_user(user_id, {'isActive': True}, r)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _apply_role(
    user_id: uuid.UUID,
    role: str,
    university_id: str | None,
    r: aioredis.Redis,
) -> dict:
    """Назначить роль с проверкой инвариантов и сбросом кэша.

    Инварианты (``EDITOR`` требует вуз, ``USER`` не привязывается) проверяет
    слой доступа, существование университета — здесь: ошибка 404 должна
    говорить администратору, что такого вуза в каталоге нет.
    """
    if university_id and role == users_db.ROLE_UNIVERSITY_REP:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')

    try:
        updated = await users_db.apply_role(user_id, role, university_id)
    except users_db.RoleInvariantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        # CHECK-ограничение БД: страховка от гонки и прямых правок данных.
        logger.warning('Role invariant violated for user %s: %s', user_id, exc)
        raise HTTPException(status_code=400, detail='Role invariant violated') from exc

    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    await safe_cache_write(cache_user_after_write(r, updated))
    return updated


@admin_page.post(
    '/role/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Role assigned'},
        400: {'description': 'Role invariant violated (EDITOR without university)'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User or university not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def assign_role(
    user_id: uuid.UUID,
    payload: RoleAssignment,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Назначить пользователю роль: ``USER``, ``EDITOR`` или ``ADMIN``.

    Роль и университет меняются одним запросом — это единственный способ
    назначить представителя, поэтому нельзя случайно получить ``EDITOR``
    без университета или привязать вуз обычному пользователю.
    """
    try:
        return await _apply_role(
            user_id,
            payload.role,
            payload.university_id,
            r,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/grant_admin/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Admin role granted'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        409: {'description': 'User is already ADMIN'},
        500: {'description': 'Internal server error'},
    },
)
async def grant_admin(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Назначить роль ADMIN (привязка к университету, если была, сохраняется)."""
    try:
        to_user = await users_db.find_user_by_id(user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') == users_db.ROLE_ADMIN:
            raise HTTPException(status_code=409, detail='User is already ADMIN')
        return await _apply_role(
            user_id,
            users_db.ROLE_ADMIN,
            to_user.get('university_id'),
            r,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/demote_admin/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Admin role removed'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        409: {'description': 'User is not ADMIN'},
        500: {'description': 'Internal server error'},
    },
)
async def demote_admin(
    user_id: uuid.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Снять роль ADMIN.

    Роль, которая остаётся дальше, выбирается по привязке: привязанный к
    университету пользователь продолжает быть его представителем
    (``EDITOR``), остальные становятся обычными пользователями (``USER``).
    """
    try:
        to_user = await users_db.find_user_by_id(user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.get('role') != users_db.ROLE_ADMIN:
            raise HTTPException(status_code=409, detail='User is not ADMIN')
        return await _apply_role(
            user_id,
            users_db.demote_role(to_user),
            to_user.get('university_id'),
            r,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/university/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'University representative assigned or detached'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User or university not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def assign_university(
    user_id: uuid.UUID,
    payload: UniversityAssignment,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Назначить или снять роль представителя университета.

    Тонкая обёртка над ``POST /admin/role/{user_id}``: привязка вуза и есть
    назначение представителя. Отдельная привязка обычному ``USER`` не
    допускается — она была бы молчаливым способом выдать права.
    """
    try:
        to_user = await users_db.find_user_by_id(user_id)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        role = (
            users_db.ROLE_UNIVERSITY_REP
            if payload.university_id
            else users_db.ROLE_USER
        )
        return await _apply_role(
            user_id,
            role,
            payload.university_id,
            r,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_page.post(
    '/archive_olympiad/{olympiad_id}',
    response_model=schemas.olympiads.OlympiadResponse,
    responses={
        200: {'description': 'Olympiad archived or restored'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Olympiad not found'},
        409: {'description': 'Olympiad is absent in the current RSOSH list and cannot be restored manually'},
        500: {'description': 'Internal server error'},
    },
)
async def archive_olympiad(
    olympiad_id: uuid.UUID,
    archived: bool = True,
    current_user: deps.AdminUser = None,
):
    """Исключить олимпиаду из актуального каталога или вернуть её.

    Статус отвечает на вопрос «есть ли олимпиада в актуальном перечне РСОШ»,
    поэтому решение о нём принимают два механизма, и это видно по причине
    архива (``archive_reason``):

    - ``MANUAL`` — администратор исключил олимпиаду руками (например, из-за
      ошибки в данных). Такую запись можно вернуть;
    - ``RSOSH_ABSENT`` — импорт не нашёл олимпиаду в перечне. Вернуть её в
      актуальные вручную нельзя (409): это сделает только импорт РСОШ, где
      олимпиада снова встретится. Иначе кнопка «вернуть» превращала бы
      олимпиаду в актуальную по перечню без всякого перечня.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')

        if archived:
            updated = await database.olympiads.edit_olympiad(
                olympiad_id,
                {'status': 'ARCHIVED', 'archive_reason': ARCHIVE_MANUAL},
            )
        else:
            if olympiad.get('archive_reason') == ARCHIVE_BY_RSOSH:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        'Олимпиада архивирована, потому что её нет в актуальном '
                        'перечне РСОШ. Вернуть её в актуальные можно только '
                        'подтверждением импорта РСОШ, где олимпиада есть.'
                    ),
                )
            updated = await database.olympiads.edit_olympiad(
                olympiad_id,
                {'status': 'PUBLISHED', 'archive_reason': None},
            )

        if not updated:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
