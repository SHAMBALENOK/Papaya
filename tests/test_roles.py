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


async def test_demote_admin_keeps_representative_role(client):
    """Снятие ADMIN возвращает роль представителя, а не голого пользователя."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    rep = await register_user(client)
    await admin_client(client)
    await set_user_role(client, rep['id'], 'EDITOR', university['id'])

    await admin_client(client)
    granted = await client.post(f"/api/v1/admin/grant_admin/{rep['id']}")
    assert granted.status_code == 200
    assert granted.json()['role'] == 'ADMIN'
    # Права администратора от привязки не зависят, но привязка сохранена.
    assert granted.json()['university_id'] == university['id']

    demoted = await client.post(f"/api/v1/admin/demote_admin/{rep['id']}")
    assert demoted.status_code == 200
    assert demoted.json()['role'] == 'EDITOR'
    assert demoted.json()['university_id'] == university['id']


async def test_demote_admin_without_university_becomes_user(client):
    await admin_client(client)
    admin = await register_user(client)
    await admin_client(client)
    await client.post(f"/api/v1/admin/grant_admin/{admin['id']}")

    demoted = await client.post(f"/api/v1/admin/demote_admin/{admin['id']}")
    assert demoted.status_code == 200
    assert demoted.json()['role'] == 'USER'
    assert demoted.json()['university_id'] is None


async def test_demote_admin_rejects_non_admin(client):
    await admin_client(client)
    user = await register_user(client)
    await admin_client(client)

    response = await client.post(f"/api/v1/admin/demote_admin/{user['id']}")
    assert response.status_code == 409
    assert response.json()['detail'] == 'User is not ADMIN'


async def test_admin_role_management(client):
    admin = await admin_client(client)
    user = await register_user(client)
    # Возвращаем сессию администратору: у клиента одна cookie-сессия.
    await login_user(client, admin['email'])

    granted = await client.post(f"/api/v1/admin/grant_admin/{user['id']}")
    assert granted.status_code == 200
    assert granted.json()['role'] == 'ADMIN'

    repeated = await client.post(f"/api/v1/admin/grant_admin/{user['id']}")
    assert repeated.status_code == 409

    demoted = await client.post(f"/api/v1/admin/demote_admin/{user['id']}")
    assert demoted.status_code == 200
    assert demoted.json()['role'] == 'USER'


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
