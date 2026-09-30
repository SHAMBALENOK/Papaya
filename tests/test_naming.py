"""Порядок названий в интерфейсе: краткое, затем полное.

Проверяется на уровне данных и шаблонов, а не «на глаз»: приоритет названий —
часть концепции, и его легко перевернуть обратно, случайно отредактировав
карточку.

Сама разметка проверяется в ``tests/test_frontend_contract.py`` (там, где
лежат проверки порядка подключения скриптов и текстов), а здесь — что API
отдаёт оба названия и что короткое не теряется в списках.
"""

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    moderate_bvi,
    university_rep_client,
)


async def test_university_keeps_both_names(client):
    university = await create_university(
        client,
        'Московский физико-технический институт',
        short_name='МФТИ',
    )
    assert university['name'] == 'Московский физико-технический институт'
    assert university['short_name'] == 'МФТИ'

    detail = await client.get(f"/api/v1/universities/{university['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body['short_name'] == 'МФТИ'
    assert body['name'] == 'Московский физико-технический институт'


async def test_short_name_is_optional(client):
    """Без краткого названия карточка показывает полное — единственное."""
    university = await create_university(
        client, 'Университет Иннополис', short_name=None
    )
    assert university['short_name'] is None

    detail = await client.get(f"/api/v1/universities/{university['id']}")
    assert detail.json()['name'] == 'Университет Иннополис'


async def test_both_names_survive_in_catalog_and_search(client):
    """Короткое название не теряется в каталоге и в поиске.

    Раньше карточка брала только одно из двух названий, и поиск по краткому
    имени при этом находил вуз — то есть находил, а показывал не то.
    """
    await create_university(
        client,
        'Национальный исследовательский университет «Высшая школа экономики»',
        short_name='НИУ ВШЭ',
    )

    catalog = await client.get('/api/v1/universities')
    assert catalog.status_code == 200
    item = catalog.json()['universities'][0]
    assert item['short_name'] == 'НИУ ВШЭ'
    assert item['name'].startswith('Национальный исследовательский')

    found = await client.get('/api/v1/search?q=НИУ ВШЭ')
    assert found.status_code == 200
    assert any(
        row.get('short_name') == 'НИУ ВШЭ' for row in found.json()['universities']
    )


async def test_university_with_bvi_keeps_olympiad_names(client):
    """Связь БВИ не теряет названия: оба у вуза, оба у олимпиады."""
    university = await create_university(
        client, 'МФТИ полное название', short_name='МФТИ'
    )
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')

    await university_rep_client(client, university['id'])
    created = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert created.status_code == 201

    await admin_client(client)
    confirmed = await moderate_bvi(
        client, university['id'], olympiad['id'], 'confirm'
    )
    assert confirmed.status_code == 200

    on_olympiad = await client.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
    assert on_olympiad.status_code == 200
    listed = on_olympiad.json()['universities'][0]
    assert listed['short_name'] == 'МФТИ'
    assert listed['name'] == 'МФТИ полное название'

    on_university = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert on_university.status_code == 200
    olympiads = on_university.json()['olympiads']
    assert [row['name'] for row in olympiads] == [
        'Олимпиада школьников «Физтех»'
    ]
