"""Ролевая модель: USER / EDITOR / ADMIN и object-level доступ к событиям."""

import uuid

from tests.conftest import promote_role, register_user


async def _create_event(client, name: str) -> dict:
    response = await client.post(
        '/api/v1/events/add_event',
        json={'name': name, 'disc': 'Автотест'},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_user_cannot_create_event(client):
    await register_user(client)
    response = await client.post(
        '/api/v1/events/add_event',
        json={'name': 'Нельзя', 'disc': ''},
    )
    assert response.status_code == 403


async def test_editor_can_create_event(client):
    user = await register_user(client)
    await promote_role(user['id'], 'EDITOR')

    created = await _create_event(client, 'Своё событие')
    assert created['owner'] == user['id']


async def test_editor_edits_own_event(client):
    user = await register_user(client)
    await promote_role(user['id'], 'EDITOR')
    event = await _create_event(client, 'Своё событие')

    edited = await client.post(
        f"/api/v1/events/edit_event/{event['id']}",
        json={'name': 'Переименовано'},
    )
    assert edited.status_code == 200
    assert edited.json()['name'] == 'Переименовано'


async def test_editor_cannot_edit_foreign_event(client):
    first = await register_user(client)
    await promote_role(first['id'], 'EDITOR')
    foreign_event = await _create_event(client, 'Событие первого редактора')

    second = await register_user(client)
    await promote_role(second['id'], 'EDITOR')

    attempt = await client.post(
        f"/api/v1/events/edit_event/{foreign_event['id']}",
        json={'name': 'Взлом'},
    )
    assert attempt.status_code == 403


async def test_admin_edits_any_event(client):
    owner = await register_user(client)
    await promote_role(owner['id'], 'EDITOR')
    event = await _create_event(client, 'Событие владельца')

    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    edited = await client.post(
        f"/api/v1/events/edit_event/{event['id']}",
        json={'name': 'Отредактировано админом'},
    )
    assert edited.status_code == 200
    assert edited.json()['name'] == 'Отредактировано админом'


async def test_admin_archives_event(client):
    """Архивация события (эквивалент удаления): ADMIN, isActive=False."""
    owner = await register_user(client)
    await promote_role(owner['id'], 'EDITOR')
    event = await _create_event(client, 'Кандидат в архив')

    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    archived = await client.post(
        f"/api/v1/admin/archive_event/{event['id']}",
    )
    assert archived.status_code == 200
    assert archived.json()['isActive'] is False

    # Архивное событие исчезает из публичного каталога.
    dashboard = await client.get('/api/v1/events/dashboard')
    names = [item['name'] for item in dashboard.json()['events']]
    assert 'Кандидат в архив' not in names

    # Но остаётся видимым в админ-панели.
    admin_events = await client.get('/api/v1/admin/events')
    body = admin_events.json()
    assert any(
        item['name'] == 'Кандидат в архив' and item['isActive'] is False
        for item in body['events']
    )


async def test_user_cannot_archive_event(client):
    user = await register_user(client)
    await promote_role(user['id'], 'EDITOR')
    event = await _create_event(client, 'Чужой архив')

    other = await register_user(client)
    response = await client.post(f"/api/v1/admin/archive_event/{event['id']}")
    assert response.status_code == 403


async def test_unknown_event_returns_404(client):
    await register_user(client)
    response = await client.get(f'/api/v1/events/{uuid.uuid4()}')
    assert response.status_code == 404


async def test_dashboard_requires_authentication(client):
    response = await client.get('/api/v1/events/dashboard')
    assert response.status_code == 401