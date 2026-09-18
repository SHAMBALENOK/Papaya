"""CRUD событий через публичный API и ограничение размера загрузок."""

import io
import uuid

import openpyxl

from tests.conftest import promote_role, register_user


async def _editor_client(client):
    """Зарегистрировать пользователя и повысить до EDITOR."""
    user = await register_user(client)
    await promote_role(user['id'], 'EDITOR')
    return user


async def test_create_and_fetch_event(client):
    await _editor_client(client)
    response = await client.post(
        '/api/v1/events/add_event',
        json={'name': 'Олимпиада теста', 'disc': 'Описание'},
    )
    assert response.status_code == 201
    event = response.json()
    assert event['name'] == 'Олимпиада теста'
    assert event['isActive'] is True
    assert 'createdAt' in event

    fetched = await client.get(f"/api/v1/events/{event['id']}")
    assert fetched.status_code == 200
    assert fetched.json()['id'] == event['id']


async def test_event_update_missing_fields_is_400(client):
    await _editor_client(client)
    event = (await client.post(
        '/api/v1/events/add_event',
        json={'name': 'Без изменений', 'disc': ''},
    )).json()
    response = await client.post(
        f"/api/v1/events/edit_event/{event['id']}",
        json={},
    )
    assert response.status_code == 400


async def test_dashboard_lists_own_events(client):
    user = await _editor_client(client)
    await client.post(
        '/api/v1/events/add_event',
        json={'name': 'Моё событие', 'disc': ''},
    )
    response = await client.get('/api/v1/events/dashboard/my_events')
    assert response.status_code == 200
    body = response.json()
    assert body['user_id'] == user['id']
    assert any(item['name'] == 'Моё событие' for item in body['events'])


def _xlsx_bytes() -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet['A1'] = 'Название олимпиады'
    sheet['A2'] = 'Импортированная олимпиада'
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


async def test_import_valid_xlsx(client):
    await _editor_client(client)
    response = await client.post(
        '/api/v1/events/add_events_via_tables',
        files={
            'file': (
                'events.xlsx',
                _xlsx_bytes(),
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
        },
    )
    assert response.status_code == 200, response.text
    events = response.json()
    assert any(event['name'] == 'Импортированная олимпиада' for event in events)


async def test_import_rejects_unknown_extension(client):
    await _editor_client(client)
    response = await client.post(
        '/api/v1/events/add_events_via_tables',
        files={'file': ('evil.exe', b'abc', 'application/octet-stream')},
    )
    assert response.status_code == 400
    assert response.json()['detail'] == 'Unsupported file format'


async def test_import_rejects_oversized_file(client):
    # MAX_UPLOAD_MB тестового окружения = 1 МБ.
    await _editor_client(client)
    oversized = b'\x00' * (2 * 1024 * 1024)
    response = await client.post(
        '/api/v1/events/add_events_via_tables',
        files={'file': ('big.xlsx', oversized, 'application/octet-stream')},
    )
    assert response.status_code == 413
    assert 'limit' in response.json()['detail']


async def test_event_details_rejects_bogus_uuid(client):
    await register_user(client)
    response = await client.get(f'/api/v1/events/{uuid.uuid4()}')
    assert response.status_code == 404