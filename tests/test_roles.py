"""Ролевая модель Papaya: USER / EDITOR (представитель университета) / ADMIN.

Проверяется, что границы полномочий не пересекаются и что роль всегда
согласована с привязкой к университету:

- обычный пользователь ничего не меняет в каталоге;
- представитель университета управляет связями своего вуза, но не создаёт
  олимпиады и не трогает чужие университеты;
- ``EDITOR`` нельзя получить без университета, а ``USER`` нельзя привязать
  к университету;
- администратор назначает и снимает роль представителя и управляет ролями
  так, чтобы после смены не оставалось противоречивых данных.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    login_user,
    promote_role,
    register_user,
    set_user_role,
    university_rep_client,
    upload_document,
)
from tests.rsosh_fixtures import xlsx_bytes


async def test_user_cannot_touch_catalog(client):
    await register_user(client)

    assert (await client.post(
        '/api/v1/olympiads/add_olympiad', json={'name': 'Нельзя'}
    )).status_code == 403
    assert (await client.post(
        '/api/v1/universities/add_university', json={'name': 'Нельзя'}
    )).status_code == 403
    assert (await client.get('/api/v1/admin/users')).status_code == 403
    assert (await client.get('/api/v1/admin/olympiads')).status_code == 403
    assert (await client.get('/api/v1/docs')).status_code == 403


async def test_user_cannot_import_documents(client):
    await register_user(client)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('rsosh.xlsx', xlsx_bytes(), 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 403


async def test_anonymous_can_read_catalogs(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    client.cookies.clear()

    assert (await client.get('/api/v1/universities')).status_code == 200
    assert (await client.get(f"/api/v1/universities/{university['id']}")).status_code == 200
    assert (await client.get('/api/v1/olympiads')).status_code == 200
    assert (await client.get(f"/api/v1/olympiads/{olympiad['id']}")).status_code == 200
    assert (await client.get('/api/v1/search?q=ИТМО')).status_code == 200


async def test_admin_has_full_access(client):
    admin = await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')

    assert (await client.get('/api/v1/admin/users')).status_code == 200
    assert (await client.get('/api/v1/admin/olympiads')).status_code == 200
    assert (await client.get('/api/v1/admin/bvi')).status_code == 200
    assert (await client.get('/api/v1/docs')).status_code == 200

    edited = await client.post(
        f"/api/v1/olympiads/edit_olympiad/{olympiad['id']}",
        json={'description': 'Описание'},
    )
    assert edited.status_code == 200
    assert edited.json()['description'] == 'Описание'

    assert (await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}"
    )).status_code == 200
    assert (await client.post(
        f"/api/v1/universities/edit_university/{university['id']}",
        json={'description': 'Описание'},
    )).status_code == 200


async def test_admin_assigns_university_representative(client):
    """Назначение представителя: роль и университет ставятся одним запросом."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    rep = await register_user(client)
    await admin_client(client)

    assigned = await set_user_role(
        client, rep['id'], 'EDITOR', university['id']
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['role'] == 'EDITOR'
    assert assigned.json()['university_id'] == university['id']

    # Назначение меняет права: представитель управляет связями своего вуза.
    await login_user(client, rep['email'])
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    linked = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert linked.status_code == 201

    # Снятие роли возвращает обычного пользователя и убирает привязку.
    await admin_client(client)
    revoked = await set_user_role(client, rep['id'], 'USER')
    assert revoked.status_code == 200
    assert revoked.json()['role'] == 'USER'
    assert revoked.json()['university_id'] is None

    await login_user(client, rep['email'])
    blocked = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert blocked.status_code == 403


async def test_representative_requires_university(client):
    """Нельзя получить роль представителя без университета."""
    await admin_client(client)
    user = await register_user(client)
    await admin_client(client)

    response = await set_user_role(client, user['id'], 'EDITOR')
    assert response.status_code == 400
    assert 'университет' in response.json()['detail']


async def test_cannot_bind_university_to_regular_user(client):
    """USER не привязывается к университету: привязка = роль представителя."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    user = await register_user(client)
    await admin_client(client)

    response = await set_user_role(
        client, user['id'], 'USER', university['id']
    )
    assert response.status_code == 400
    assert 'USER' in response.json()['detail']


async def test_representative_university_can_be_changed(client):
    await admin_client(client)
    first = await create_university(client, 'Университет ИТМО')
    second = await create_university(client, 'Университет МФТИ')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    rep = await register_user(client)
    await admin_client(client)

    await set_user_role(client, rep['id'], 'EDITOR', first['id'])
    moved = await set_user_role(client, rep['id'], 'EDITOR', second['id'])
    assert moved.status_code == 200
    assert moved.json()['university_id'] == second['id']

    # Права следуют за новым вузом: старый больше недоступен.
    await login_user(client, rep['email'])
    assert (await client.post(
        f"/api/v1/universities/{first['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )).status_code == 403
    assert (await client.post(
        f"/api/v1/universities/{second['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )).status_code == 201


async def test_representative_role_rejects_unknown_university(client):
    import uuid as uuid_mod

    await admin_client(client)
    user = await register_user(client)
    await admin_client(client)

    response = await set_user_role(
        client, user['id'], 'EDITOR', str(uuid_mod.uuid4())
    )
    assert response.status_code == 404
    assert response.json()['detail'] == 'University not found'


async def test_unknown_role_is_validation_error(client):
    await admin_client(client)
    user = await register_user(client)
    await admin_client(client)

    response = await set_user_role(client, user['id'], 'SUPERUSER')
    assert response.status_code == 422


async def test_role_endpoint_requires_admin(client):
    user = await register_user(client)
    response = await set_user_role(
        client, user['id'], 'EDITOR', str(uuid.uuid4())
    )
    assert response.status_code == 403


async def test_role_endpoint_is_the_only_way_to_change_role(client):
    """Legacy-маршруты смены роли удалены и не должны вернуться.

    ``grant_admin``/``demote_admin`` меняли роль, не трогая привязку к
    университету, то есть давали второй путь, на котором инварианты роли
    могли разойтись с тем, что проверяет ``/role``. Возможность повысить и
    снять роль осталась — через ``/role``, см. тесты выше и ниже.
    """
    await admin_client(client)
    user = await register_user(client)
    await admin_client(client)

    for path in ('grant_admin', 'demote_admin'):
        response = await client.post(f"/api/v1/admin/{path}/{user['id']}")
        # 404 — пути нет вовсе, 405 — путь совпал, но метод другой. В обоих
        # случаях изменить роль этим нельзя.
        assert response.status_code in (404, 405), (path, response.status_code)

    schema = await client.get('/openapi.json')
    paths = schema.json()['paths']
    assert not [p for p in paths if 'grant_admin' in p or 'demote_admin' in p], (
        'в схеме API не должно быть отдельных маршрутов смены роли'
    )

    # Пока маршрутов нет, роль по-прежнему меняется одной операцией.
    still_works = await set_user_role(client, user['id'], 'ADMIN')
    assert still_works.status_code == 200
    assert still_works.json()['role'] == 'ADMIN'


async def test_role_change_keeps_or_drops_university_by_target_role(client):
    """Роль и привязка меняются вместе: результат задаёт целевая роль.

    Раньше «куда попадёт человек после снятия ADMIN» решал сервер внутри
    ``demote_admin``. Теперь решение принимает администратор в том же запросе,
    а инвариант («EDITOR обязан быть привязан, USER — не привязан») проверяет
    сервер. Здесь проверяются оба допустимых исхода.
    """
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    rep = await register_user(client)
    await admin_client(client)
    await set_user_role(client, rep['id'], 'EDITOR', university['id'])

    # Повышение до ADMIN сохраняет привязку: она ему не мешает.
    promoted = await set_user_role(
        client, rep['id'], 'ADMIN', university['id']
    )
    assert promoted.status_code == 200
    assert promoted.json()['role'] == 'ADMIN'
    assert promoted.json()['university_id'] == university['id']

    # Возврат к представителю — вместе с университетом.
    back_to_rep = await set_user_role(
        client, rep['id'], 'EDITOR', university['id']
    )
    assert back_to_rep.status_code == 200
    assert back_to_rep.json()['role'] == 'EDITOR'
    assert back_to_rep.json()['university_id'] == university['id']

    # Обычный пользователь привязки не получает: привязку нужно снять явно.
    dropped = await set_user_role(client, rep['id'], 'USER', None)
    assert dropped.status_code == 200
    assert dropped.json()['role'] == 'USER'
    assert dropped.json()['university_id'] is None


async def test_admin_role_management(client):
    admin = await admin_client(client)
    user = await register_user(client)
    # Возвращаем сессию администратору: у клиента одна cookie-сессия.
    await login_user(client, admin['email'])

    granted = await set_user_role(client, user['id'], 'ADMIN')
    assert granted.status_code == 200
    assert granted.json()['role'] == 'ADMIN'

    # Повторное назначение той же роли — тоже успех, а не ошибка: запрос
    # идемпотентен по смыслу (роль уже такая).
    repeated = await set_user_role(client, user['id'], 'ADMIN')
    assert repeated.status_code == 200
    assert repeated.json()['role'] == 'ADMIN'

    demoted = await set_user_role(client, user['id'], 'USER')
    assert demoted.status_code == 200
    assert demoted.json()['role'] == 'USER'


async def test_editor_without_university_is_rejected(client):
    """EDITOR без университета отклоняется — это инвариант, а не деталь UI."""
    await admin_client(client)
    user = await register_user(client)
    await admin_client(client)

    response = await client.post(
        f"/api/v1/admin/role/{user['id']}",
        json={'role': 'EDITOR', 'university_id': None},
    )
    assert response.status_code == 400, response.text
    assert 'университет' in response.json()['detail'].lower()


async def test_ban_and_unban_user(client):
    admin = await admin_client(client)
    user = await register_user(client)
    await login_user(client, admin['email'])

    banned = await client.post(f"/api/v1/admin/ban/{user['id']}")
    assert banned.status_code == 200
    assert banned.json()['isActive'] is False

    unbanned = await client.post(f"/api/v1/admin/unban/{user['id']}")
    assert unbanned.status_code == 200
    assert unbanned.json()['isActive'] is True


async def test_rep_cannot_import_documents(client):
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])

    assert (await client.post(
        '/api/v1/docs/upload',
        files={'file': ('rsosh.xlsx', xlsx_bytes(), 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )).status_code == 403
    assert (await client.get('/api/v1/admin/bvi')).status_code == 403
