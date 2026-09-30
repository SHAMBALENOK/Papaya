"""Инварианты, которые не должны нарушаться: «не удалять» и атомарность.

Два правила, которые ломаются не тестами конкретных функций, а самим фактом
их существования:

- олимпиады и университеты не удаляются физически — только архивируются;
- система не должна остаться без активного администратора, в том числе при
  параллельных административных операциях.
"""

import asyncio
import uuid

import pytest

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    login_user,
    register_user,
    set_user_role,
)


# ------------------------- Принцип «не удалять» -------------------------


def test_no_physical_delete_in_data_layer():
    """В слоях данных нет функций физического удаления каталога.

    У олимпиады есть история: подтверждённые связи БВИ, документ-источник, путь
    по перечню РСОШ. Удаление строки стёрло бы её вместе с подтверждёнными
    заявками университетов, поэтому единственный путь — архивирование.
    """
    from app.database import olympiads, universities

    for module in (olympiads, universities):
        deletes = [
            name
            for name in dir(module)
            if name.startswith('delete_') and callable(getattr(module, name))
        ]
        assert not deletes, f'{module.__name__}: физическое удаление {deletes}'


def test_no_delete_endpoint_in_api():
    """В API нет ни одного маршрута удаления каталога."""
    from app.main import app

    paths = app.openapi()['paths']
    destructive = [
        path
        for path in paths
        if 'delete' in path.lower() or 'remove' in path.lower() and 'olympiad' in path
    ]
    assert not destructive, destructive


async def test_archived_olympiad_is_not_in_public_catalog(client):
    """Архивная олимпиада исчезает из актуального каталога, но не из БД.

    Публично её нет, а по прямой ссылке страница открывается и отдаёт данные:
    архив — это пометка, а не удаление.
    """
    olympiad = await create_olympiad(client, 'Олимпиада в архиве')
    await client.post(f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true")

    catalog = await client.get('/api/v1/olympiads')
    assert olympiad['id'] not in [row['id'] for row in catalog.json()['olympiads']]

    detail = await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    assert detail.status_code == 200
    assert detail.json()['name'] == 'Олимпиада в архиве'
    assert detail.json()['status'] == 'ARCHIVED'

    with_archived = await client.get('/api/v1/olympiads?include_archived=true')
    assert olympiad['id'] in [row['id'] for row in with_archived.json()['olympiads']]


async def test_import_keeps_confirmed_bvi_links(client):
    """Импорт РСОШ не трогает связи БВИ: он меняет только актуальность.

    Если бы импорт удалял или обнулял связи, подтверждённая льгота исчезла бы
    из-за обновления перечня — а это неверно: университет никуда не делся.
    """
    from tests.conftest import moderate_bvi, university_rep_client

    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада с БВИ')
    await university_rep_client(client, university['id'])
    created = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert created.status_code == 201
    await admin_client(client)
    assert (
        await moderate_bvi(client, university['id'], olympiad['id'], 'confirm')
    ).status_code == 200

    # Повторный импорт другого документа РСОШ: олимпиады и связи на месте.
    from tests.conftest import run_import, upload_document
    from tests.rsosh_fixtures import xlsx_bytes

    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])
    assert (
        await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})
    ).status_code == 200

    client.cookies.clear()
    page = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert page.status_code == 200
    ids = [row['id'] for row in page.json()['olympiads']]
    assert olympiad['id'] in ids, 'импорт не должен убирать подтверждённые связи'

    detail = await client.get(f"/api/v1/universities/{university['id']}")
    assert detail.status_code == 200, 'импорт не должен удалять университет'


async def test_import_keeps_source_document(client):
    """Импорт не уничтожает документ-источник: по нему и виден источник."""
    from tests.conftest import run_import, upload_document
    from tests.rsosh_fixtures import xlsx_bytes

    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])
    await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})

    catalog = await client.get('/api/v1/olympiads')
    assert catalog.json()['olympiads']

    docs = await client.get('/api/v1/docs')
    assert docs.status_code == 200
    assert any(item['id'] == doc['id'] for item in docs.json()['docs'])


# ------------------------- Атомарность защиты администратора -------------------------


async def _active_admin_count() -> int:
    from sqlalchemy import func, select

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Users).where(
                Users.role == 'ADMIN', Users.isActive.is_(True)
            )
        )
    return result.scalar()


async def test_demote_and_ban_in_parallel_never_leave_zero_admins(client):
    """Параллельные операции не могут оставить систему без администратора.

    Опасная комбинация — два администратора, и две операции сразу: первая
    понижает первого администратора, вторая блокирует второго. По отдельности
    каждая проверка выглядит безобидно: при понижении первого «остаётся
    второй», при блокировке второго «остаётся первый». Вместе они дают ноль
    администраторов.

    Без блокировки строк администраторов вторая операция увидела бы неcommitted
    состояние первой, посчитала бы «первый ещё администратор» и тоже прошла бы.
    С ``SELECT ... FOR UPDATE`` вторая операция ждёт первую и пересчитывает уже
    по фактическому состоянию — поэтому одна из них получает отказ.

    Проверяется слой данных: там находится сама блокировка, и параллельность
    настоящая — каждая операция работает в своей сессии.
    """
    from app.database import users as users_db

    first = await admin_client(client)
    second = await register_user(client)
    await login_user(client, first['email'])
    assert (await set_user_role(client, second['id'], 'ADMIN')).status_code == 200
    assert await _active_admin_count() == 2

    outcomes = await asyncio.gather(
        users_db.apply_role_guarded(first['id'], 'USER'),
        users_db.set_active_guarded(second['id'], False),
    )

    refused = [
        item for item in outcomes
        if isinstance(item, str) and item == users_db.ADMIN_GUARD_LAST_ADMIN
    ]
    assert len(refused) == 1, outcomes
    assert await _active_admin_count() == 1, 'должен остаться один администратор'


async def test_parallel_demotions_of_two_admins_are_allowed(client):
    """Два разных администратора понижаются одновременно — это разрешено.

    Каждая операция убирает своего человека и оставляет другого, поэтому обе
    законны: запрет нацелен на «не осталось ни одного», а не на количество
    операций.
    """
    from app.database import users as users_db

    first = await admin_client(client)
    second = await register_user(client)
    third = await register_user(client)
    await login_user(client, first['email'])
    await set_user_role(client, second['id'], 'ADMIN')
    await set_user_role(client, third['id'], 'ADMIN')
    assert await _active_admin_count() == 3

    outcomes = await asyncio.gather(
        users_db.apply_role_guarded(first['id'], 'USER'),
        users_db.apply_role_guarded(second['id'], 'USER'),
    )
    assert not [item for item in outcomes if isinstance(item, str)], outcomes
    assert await _active_admin_count() == 1


async def test_parallel_operations_on_the_last_admin_are_refused(client):
    """Единственный администратор: сколько ни проси — отказ всем."""
    from app.database import users as users_db

    admin = await admin_client(client)
    assert await _active_admin_count() == 1

    outcomes = await asyncio.gather(
        users_db.apply_role_guarded(admin['id'], 'USER'),
        users_db.set_active_guarded(admin['id'], False),
        users_db.apply_role_guarded(admin['id'], 'USER'),
    )
    assert all(
        item == users_db.ADMIN_GUARD_LAST_ADMIN for item in outcomes
    ), outcomes
    assert await _active_admin_count() == 1


async def test_missing_user_is_not_reported_as_last_admin(client):
    """Отсутствующий пользователь — это «не найден», а не «последний админ»."""
    from app.database import users as users_db

    outcome = await users_db.apply_role_guarded(str(uuid.uuid4()), 'USER')
    assert outcome == users_db.ADMIN_GUARD_MISSING

    banned = await users_db.set_active_guarded(str(uuid.uuid4()), False)
    assert banned == users_db.ADMIN_GUARD_MISSING


# ------------------------- Повторная заявка и обходы -------------------------


async def test_repeated_request_for_archived_olympiad_still_rejected(client):
    """Повторная заявка не обходит запрет на архивную олимпиаду.

    Заявка идемпотентна: для актуальной олимпиады повтор возвращает существующую
    связь. Но для архивной проверка актуальности стоит до обращения к данным, и
    повтор тоже отклоняется — иначе запрет обходился бы двумя кликами.
    """
    from tests.conftest import moderate_bvi, university_rep_client

    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада вне перечня')
    await university_rep_client(client, university['id'])
    assert (
        await client.post(
            f"/api/v1/universities/{university['id']}/bvi",
            json={'olympiad_id': olympiad['id']},
        )
    ).status_code == 201

    await admin_client(client)
    await client.post(f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true")

    for _ in range(2):
        repeat = await client.post(
            f"/api/v1/universities/{university['id']}/bvi",
            json={'olympiad_id': olympiad['id']},
        )
        assert repeat.status_code == 409, repeat.text

    # И администратор не может завести новую связь с архивной олимпиадой:
    # иначе запрет обходился бы ролью.
    admin_request = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert admin_request.status_code == 409


async def test_archived_olympiad_absent_from_picker_catalog(client):
    """Каталог для выбора олимпиады не содержит архивных записей.

    Это frontend-часть запрета: представитель физически не может выбрать
    архивную олимпиаду, даже если подставит её id вручную (тогда сработает 409
    на сервере).
    """
    olympiad = await create_olympiad(client, 'Олимпиада вне перечня')
    await client.post(f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true")

    catalog = await client.get('/api/v1/olympiads')
    assert olympiad['id'] not in [row['id'] for row in catalog.json()['olympiads']]
