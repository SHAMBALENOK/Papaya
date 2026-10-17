"""Администрирование Papaya.

Администратор отвечает за каталог и его наполнение:

- пользователи: блокировка, роли, привязка представителя к университету;
- олимпиады: архивирование/возврат из архива, ручное создание и правка;
- заявки БВИ: подтверждение и снятие связей университет ↔ олимпиада.

Все маршруты требуют роль ``ADMIN``: проверка общая и живёт в
``app.core.deps.require_admin``.

Роль и привязка к университету меняются только через
``POST /admin/role/{user_id}``: представитель — это «роль + вуз», поэтому
отдельного маршрута «привязать университет» нет. Два способа назначить
представителя означали бы, что один из них обходит проверки инварианта.
"""

import logging
import uuid
from typing import List

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError

from app import database, schemas
from app.caching.main import cache_user_after_write, get_redis
from app.core import audit, deps, rate_limit
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
    # Всего пользователей под фильтром: панели нужно отличать «список кончился»
    # от «показана только первая страница».
    total: int = 0


class AdminOlympiadListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    # Причина архива нужна панели: по ней понятно, можно ли вернуть запись
    # вручную. Без неё интерфейс предлагал «Вернуть» для олимпиады,
    # исчезнувшей из перечня РСОШ, и получал 409.
    archive_reason: str | None = None
    source_doc_id: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class AdminOlympiadsResponse(BaseModel):
    olympiads: List[AdminOlympiadListItem]
    # Всего олимпиад под фильтром — для постраничной выдачи панели.
    total: int = 0


class AdminBviListItem(BaseModel):
    id: str | None = None
    university_id: str | None = None
    university_name: str | None = None
    olympiad_id: str | None = None
    olympiad_name: str | None = None
    status: str | None = None
    # Авторы решения: кто заявил и кто подтвердил. Без этого очередь модерации
    # не отвечает на вопрос «это точно тот вуз? и кто это подтвердил?».
    createdBy: str | None = None
    confirmedBy: str | None = None
    # Актуальна ли олимпиада: по архивной новая заявка невозможна, и
    # администратор должен видеть это до нажатия кнопок.
    olympiad_status: str | None = None
    createdAt: str | None = None


class AdminBviResponse(BaseModel):
    links: List[AdminBviListItem]
    # Всего связей под фильтром — сколько бы ни вернула страница. Нужно панели,
    # чтобы отличить «связей нет» от «показана только первая страница».
    total: int = 0


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
async def list_users(
    search: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    """Все пользователи, включая заблокированных.

    Поддерживает поиск по имени/фамилии/email и постраничную выдачу
    (``limit``/``offset``): панель не должна тянуть весь список, чтобы показать
    первые строки. ``total`` отвечает, сколько пользователей под фильтром всего.
    Без ``limit`` возвращаются все — так остаются совместимыми вызовы, которым
    нужен полный список.
    """
    try:
        users = await database.users.list_users(
            include_inactive=True,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = await database.users.count_users(include_inactive=True, search=search)
        # Словарь, а не JSONResponse: response_model=AdminUsersResponse
        # проверит контракт и отсечёт лишние поля. _serialize_user уже
        # перечисляет разрешённые поля явно, хэша пароля среди них нет.
        return {
            'users': [_serialize_user(user) for user in users],
            'total': total,
        }
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
async def list_olympiads(
    search: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    """Каталог олимпиад включая архивные (вне актуального перечня РСОШ).

    В отличие от публичного каталога содержит служебные поля: причина архива
    (чтобы понимать, можно ли вернуть запись) и документ-источник (чтобы видеть,
    откуда взялись данные). Поддерживает поиск и постраничную выдачу.
    """
    try:
        olympiads = await database.olympiads.list_olympiads(
            status=None,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = await database.olympiads.count_olympiads(status=None, search=search)
        return {
            'olympiads': [
                {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'status': item.get('status'),
                    'archive_reason': item.get('archive_reason'),
                    'source_doc_id': item.get('source_doc_id'),
                    'createdAt': item.get('createdAt'),
                    'updatedAt': item.get('updatedAt'),
                }
                for item in olympiads
            ],
            'total': total,
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
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    """Очередь модерации: заявки университетов на связи БВИ.

    Для каждой связи видно авторов решения (кто заявил, кто подтвердил) и
    актуальность олимпиады: по архивной заявку уже нельзя подать, но
    подтверждение администратора по ней может быть и историческим, и
    осмысленным.

    Страница ограничена ``limit``/``offset``, а названия вуза и олимпиады
    подтягиваются одним JOIN-ом: очередь не должна замедляться линейно с ростом
    каталога. ``total`` отвечает, сколько связей есть под фильтром всего.
    """
    try:
        links = await database.bvi.list_links_enriched(
            status=status, limit=limit, offset=offset
        )
        total = await database.bvi.count_links(status=status)
        return {'links': links, 'total': total}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


def _raise_admin_guard_error(outcome, action: str) -> None:
    """Превратить отказ защиты в понятный 409.

    Сама проверка атомарна и живёт в слое данных
    (``apply_role_guarded`` / ``set_active_guarded``): здесь только перевод
    результата в HTTP-ошибку. Отдельный предварительный подсчёт администраторов
    был бы гонкой — две параллельные операции могли бы обе решить, что
    понижаемый не последний.
    """
    if outcome == users_db.ADMIN_GUARD_LAST_ADMIN:
        raise HTTPException(
            status_code=409,
            detail=(
                f'Нельзя {action}: это последний активный администратор Papaya. '
                'Сначала назначьте другого администратора.'
            ),
        )
    if outcome == users_db.ADMIN_GUARD_MISSING:
        raise HTTPException(status_code=404, detail='User not found')


@admin_page.post(
    '/ban/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'User banned successfully'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'User not found'},
        409: {'description': 'Target is the last active admin'},
        500: {'description': 'Internal server error'},
    },
)
async def ban(
    user_id: uuid.UUID,
    request: Request,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Заблокировать пользователя (isActive = False).

    Последнего активного администратора заблокировать нельзя (409): зайти в
    панель будет некому. Проверка выполняется в той же транзакции и под
    блокировкой строк администраторов, поэтому параллельные операции не могут
    оставить систему без администратора.
    """
    try:
        updated = await users_db.set_active_guarded(user_id, False)
        if isinstance(updated, str):
            _raise_admin_guard_error(updated, 'заблокировать')
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated))
        audit.log_admin_action(
            'ban',
            actor_id=current_user.get('id'),
            target_id=user_id,
            ip=rate_limit.client_ip(request),
        )
        return updated
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
    request: Request,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Разблокировать пользователя (isActive = True)."""
    try:
        updated = await users_db.set_active_guarded(user_id, True)
        if isinstance(updated, str):
            _raise_admin_guard_error(updated, 'разблокировать')
            raise HTTPException(status_code=404, detail='User not found')
        await safe_cache_write(cache_user_after_write(r, updated))
        audit.log_admin_action(
            'unban',
            actor_id=current_user.get('id'),
            target_id=user_id,
            ip=rate_limit.client_ip(request),
        )
        return updated
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
    *,
    actor_id,
    ip: str | None = None,
) -> dict:
    """Назначить роль с проверкой инвариантов и сбросом кэша.

    Инварианты (``EDITOR`` требует вуз, ``USER`` не привязывается) проверяет
    слой доступа, существование университета — здесь: ошибка 404 должен
    говорить администратору, что такого вуза в каталоге нет.

    Запрет на снятие роли у последнего активного администратора проверяется
    атомарно в слое данных, а не отдельным предварительным подсчётом: счёт
    разъезжается с фактическим состоянием при параллельных запросах.

    Своя роль не меняется: иначе администратор мог бы снять права сам с себя
    (и, при единственном админе, заблокировать управление), либо повысить себя
    в обход осознанного решения. Ограничение на сервере, а не только в UI.
    Исключение — понижение последнего администратора: там срабатывает более
    конкретный запрет (409), поэтому его проверяем раньше собственной роли.

    Единственная точка изменения роли — ``/role``. Отдельные ``/grant_admin`` и
    ``/demote_admin`` удалены: они меняли бы роль и привязку разными
    операциями, то есть давали второй путь, на котором инварианты могли бы
    разойтись с тем, что проверяет ``/role``.
    """
    before = await database.users.find_user_by_id(str(user_id))
    if not before:
        raise HTTPException(status_code=404, detail='User not found')

    if str(user_id) == str(actor_id):
        demotes_last_admin = (
            before.get('role') == users_db.ROLE_ADMIN
            and before.get('isActive', False)
            and role != users_db.ROLE_ADMIN
            and await database.users.is_last_active_admin(str(user_id))
        )
        if demotes_last_admin:
            # Тот же запрет, что и на чужой роли, но важнее: не оставить
            # систему без администратора. Ошибка та же — 409, не 403.
            _raise_admin_guard_error(
                users_db.ADMIN_GUARD_LAST_ADMIN, 'снять роль администратора'
            )
        raise HTTPException(
            status_code=403,
            detail='Нельзя менять роль у себя',
        )

    if university_id and role == users_db.ROLE_UNIVERSITY_REP:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')

    try:
        updated = await users_db.apply_role_guarded(user_id, role, university_id)
    except users_db.RoleInvariantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        # CHECK-ограничение БД: страховка от гонки и прямых правок данных.
        logger.warning('Role invariant violated for user %s: %s', user_id, exc)
        raise HTTPException(status_code=400, detail='Role invariant violated') from exc

    if isinstance(updated, str):
        _raise_admin_guard_error(updated, 'снять роль администратора')
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    await safe_cache_write(cache_user_after_write(r, updated))
    audit.log_role_change(
        actor_id=actor_id,
        target_id=user_id,
        old_role=before.get('role'),
        new_role=role,
        university_id=university_id,
        ip=ip,
    )
    return updated


@admin_page.post(
    '/role/{user_id}',
    response_model=schemas.users.UserResponse,
    responses={
        200: {'description': 'Role assigned'},
        400: {'description': 'Role invariant violated (EDITOR without university)'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required or attempt to change own role'},
        404: {'description': 'User or university not found'},
        409: {'description': 'Target is the last active admin'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def assign_role(
    user_id: uuid.UUID,
    payload: RoleAssignment,
    request: Request,
    r: aioredis.Redis = Depends(get_redis),
    current_user: deps.AdminUser = None,
):
    """Назначить пользователю роль: ``USER``, ``EDITOR`` или ``ADMIN``.

    Это единственный способ изменить роль, и роль вместе с университетом
    меняется одним запросом: так нельзя случайно получить ``EDITOR`` без
    университета или привязать вуз обычному пользователю.

    Повысить до ``ADMIN`` и понизить можно только здесь — отдельных
    ``grant_admin``/``demote_admin`` в API нет.
    """
    try:
        return await _apply_role(
            user_id,
            payload.role,
            payload.university_id,
            r,
            actor_id=current_user.get('id'),
            ip=rate_limit.client_ip(request),
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
            # Ручной архив уже стоит (или причина другая) — повторный запрос
            # ничего не меняет. Нельзя перезаписывать ``RSOSH_ABSENT`` на
            # ``MANUAL``: архив «нет в перечне РСОШ» снимается только импортом,
            # и ручная пометка забрала бы у него эту возможность.
            if olympiad.get('status') == 'ARCHIVED':
                return olympiad
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
