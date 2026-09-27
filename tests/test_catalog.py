"""Каталоги Papaya: университеты, олимпиады, поиск, страницы сущностей.

Проверяется основной пользовательский сценарий на уровне API:
каталоги читаются без авторизации, а страницы отдают связанные данные.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    register_user,
)


async def test_universities_catalog_is_public(client):
    """Гость видит каталог университетов без входа."""
    await create_university(client, 'Университет ИТМО', short_name='ИТМО')

    response = await client.get('/api/v1/universities')
    assert response.status_code == 200
    names = [item['name'] for item in response.json()['universities']]
    assert 'Университет ИТМО' in names


async def test_university_details_and_404(client):
    university = await create_university(
        client,
        'Московский физико-технический институт',
        short_name='МФТИ',
        website='https://mipt.ru',
        description='Федеральный университет',
    )

    detail = await client.get(f"/api/v1/universities/{university['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body['short_name'] == 'МФТИ'
    assert body['website'] == 'https://mipt.ru'

    missing = await client.get(f'/api/v1/universities/{uuid.uuid4()}')
    assert missing.status_code == 404


async def test_create_university_requires_admin(client):
    """Обычный пользователь не может завести университет."""
    await register_user(client)
    response = await client.post(
        '/api/v1/universities/add_university',
        json={'name': 'Чужой университет'},
    )
    assert response.status_code == 403


async def test_duplicate_university_is_rejected(client):
    """Один и тот же вуз нельзя завести дважды (даже с другим написанием)."""
    await create_university(client, 'Университет ИТМО')
    await admin_client(client)

    response = await client.post(
        '/api/v1/universities/add_university',
        json={'name': '  университет   итмо  '},
    )
    assert response.status_code == 409
    assert response.json()['detail'] == 'University with this name already exists'


async def test_admin_edits_university(client):
    university = await create_university(client, 'Университет ИТМО')

    edited = await client.post(
        f"/api/v1/universities/edit_university/{university['id']}",
        json={'description': 'Описание вуза', 'short_name': 'ИТМО'},
    )
    assert edited.status_code == 200
    assert edited.json()['description'] == 'Описание вуза'

    empty = await client.post(
        f"/api/v1/universities/edit_university/{university['id']}",
        json={},
    )
    assert empty.status_code == 400


async def test_olympiads_catalog_is_public_and_searchable(client):
    await create_olympiad(
        client,
        'Всероссийская олимпиада школьников «Физтех»',
        description='Ежегодная олимпиада',
    )
    await create_olympiad(client, 'Олимпиада школьников «Ломоносов»')

    catalog = await client.get('/api/v1/olympiads')
    assert catalog.status_code == 200
    assert len(catalog.json()['olympiads']) >= 2

    found = await client.get('/api/v1/olympiads?search=Физтех')
    assert found.status_code == 200
    names = [item['name'] for item in found.json()['olympiads']]
    assert names == ['Всероссийская олимпиада школьников «Физтех»']


async def test_search_matches_multiline_and_partial_names(client):
    """Поиск не ломается о переносы строк в названии (импорт РСОШ)."""
    await create_olympiad(client, 'Всероссийская\nолимпиада\nшкольников «Высшая проба»')
    await create_olympiad(client, 'Олимпиада школьников «Физтех»')

    response = await client.get('/api/v1/olympiads?search=высшая проба')
    assert response.status_code == 200
    names = [item['name'] for item in response.json()['olympiads']]
    assert len(names) == 1
    assert 'Высшая проба' in names[0]


async def test_duplicate_olympiad_is_rejected(client):
    await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await admin_client(client)

    response = await client.post(
        '/api/v1/olympiads/add_olympiad',
        json={'name': 'олимпиада школьников   «физтех»'},
    )
    assert response.status_code == 409


async def test_create_olympiad_requires_admin(client):
    await register_user(client)
    response = await client.post(
        '/api/v1/olympiads/add_olympiad',
        json={'name': 'Новая олимпиада'},
    )
    assert response.status_code == 403


async def test_archived_olympiad_hidden_from_public_catalog(client):
    olympiad = await create_olympiad(client, 'Олимпиада вне перечня')

    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}"
    )
    assert archived.status_code == 200
    assert archived.json()['status'] == 'ARCHIVED'

    public = await client.get('/api/v1/olympiads')
    assert all(
        item['id'] != olympiad['id'] for item in public.json()['olympiads']
    )

    with_archived = await client.get('/api/v1/olympiads?include_archived=true')
    assert any(
        item['id'] == olympiad['id'] for item in with_archived.json()['olympiads']
    )

    restored = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=false"
    )
    assert restored.json()['status'] == 'PUBLISHED'


async def test_unified_search_returns_both_catalogs(client):
    university = await create_university(client, 'Университет ИТМО', short_name='ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Ломоносов»')

    response = await client.get('/api/v1/search?q=ИТМО')
    assert response.status_code == 200
    body = response.json()
    assert any(item['id'] == university['id'] for item in body['universities'])
    assert body['olympiads'] == []

    response = await client.get('/api/v1/search?q=Ломоносов')
    body = response.json()
    assert any(item['id'] == olympiad['id'] for item in body['olympiads'])


async def test_search_without_query_returns_empty_lists(client):
    response = await client.get('/api/v1/search?q=')
    assert response.status_code == 200
    body = response.json()
    assert body['universities'] == []
    assert body['olympiads'] == []


async def test_spa_fallback_serves_index(client):
    """Неизвестный не-API маршрут отдаёт SPA, а не JSON 404."""
    response = await client.get('/universities/1')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'Papaya' in response.text
