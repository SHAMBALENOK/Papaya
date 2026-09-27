"""Ролевая модель Papaya: USER / EDITOR (представитель университета) / ADMIN.

Проверяется, что границы полномочий не пересекаются:

- обычный пользователь ничего не меняет в каталоге;
- представитель университета управляет связями своего вуза, но не создаёт
  олимпиады и не трогает чужие университеты;
- администратор имеет полный доступ и может назначить представителя.
"""

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    login_user,
    promote_role,
    register_user,
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
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    rep = await register_user(client)
    await admin_client(client)

    assigned = await client.post(
        f"/api/v1/admin/university/{rep['id']}",
        json={'university_id': university['id']},
    )
    assert assigned.status_code == 200
    assert assigned.json()['university_id'] == university['id']

    # Назначение меняет права: представитель управляет связями своего вуза.
    await promote_role(rep['id'], 'EDITOR')
    await login_user(client, rep['email'])
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    linked = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert linked.status_code == 201

    await admin_client(client)
    detached = await client.post(
        f"/api/v1/admin/university/{rep['id']}",
        json={'university_id': None},
    )
    assert detached.status_code == 200
    assert detached.json()['university_id'] is None

    await login_user(client, rep['email'])
    blocked = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert blocked.status_code == 403


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
