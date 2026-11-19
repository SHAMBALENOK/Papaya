"""Порядок названий в интерфейсе: краткое, затем полное.

Проверяется на уровне данных и шаблонов, а не «на глаз»: приоритет названий —
часть концепции, и его легко перевернуть обратно, случайно отредактировав
карточку.

Сама разметка проверяется в ``tests/test_frontend_contract.py`` (там, где
лежат проверки порядка подключения скриптов и текстов), а здесь — что API
отдаёт оба названия и что короткое не теряется в списках.
"""

from tests.conftest import (
    create_benefit_rule,
    create_olympiad,
    create_profile,
    create_season,
    create_university,
    upload_university_doc,
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


async def test_benefit_rule_keeps_names_on_both_sides(client):
    """Правило льготы не теряет названия: оба у вуза, оба у олимпиады."""
    university = await create_university(
        client, 'МФТИ полное название', short_name='МФТИ'
    )
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    season = await create_season(client, olympiad['id'])
    profile = await create_profile(client, season['id'])
    doc = await upload_university_doc(client, university['id'])
    rule = await create_benefit_rule(
        client, university['id'], olympiad['id'], season['id'],
        profile['id'], doc['id'],
    )

    on_university = await client.get(
        f"/api/v1/universities/{university['id']}/benefits"
    )
    assert on_university.status_code == 200
    listed = next(
        row for row in on_university.json()['rules'] if row['id'] == rule['id']
    )
    assert listed['olympiad_name'] == 'Олимпиада школьников «Физтех»'

    on_olympiad = await client.get(
        f"/api/v1/benefits/olympiad/{olympiad['id']}"
    )
    assert on_olympiad.status_code == 200
    row = next(
        item for item in on_olympiad.json()['rules'] if item['id'] == rule['id']
    )
    assert row['university_short_name'] == 'МФТИ'
    assert row['university_name'] == 'МФТИ полное название'
