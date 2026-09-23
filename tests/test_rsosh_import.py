"""RSOSH-импорт: lifecycle (upload -> pipeline -> preview -> confirm/reject).

Celery-воркер в тестовом окружении не запущен, поэтому пайплайн
(``app.rsosh.processor.run_import``) выполняется напрямую из теста; HTTP-слой
проверяется для preview/confirm/reject.
"""

from io import BytesIO

import pandas as pd
import pytest

from tests.conftest import promote_role, register_user

XLSX_MIME = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)


def _make_xlsx(rows: list[tuple]) -> bytes:
    """Собрать XLSX в памяти с шапкой RSOSH-перечня."""
    table = pd.DataFrame(
        rows,
        columns=['№', 'Название олимпиады', 'Предметы (профиль)', 'Уровень'],
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        table.to_excel(writer, index=False)
    return buffer.getvalue()


async def _setup_admin_and_org(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Оргкомитет олимпиад', 'type': 'ORGANIZER'},
        )
    ).json()
    return org


async def _upload_list(client, org, content: bytes, name: str = 'list.xlsx'):
    return await client.post(
        '/api/v1/docs',
        params={'type': 'RSOSH_LIST', 'organization_id': org['id']},
        files={'file': (name, content, XLSX_MIME)},
    )


async def test_rsosh_import_lifecycle(client):
    org = await _setup_admin_and_org(client)
    uploaded = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Альфа', 'математика', '2'),
                    ('2', 'Олимпиада Бета', 'физика; информатика', '1')]),
    )
    assert uploaded.status_code == 201, uploaded.text
    doc = uploaded.json()

    from app.rsosh.processor import run_import

    section = await run_import(str(doc['id']))
    assert section['state'] == 'review'
    assert section['summary']['total'] == 2
    assert section['summary']['new'] == 2

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body['candidates']) == 2
    names = {c['name'] for c in body['candidates']}
    assert names == {'Олимпиада Альфа', 'Олимпиада Бета'}

    # До confirm в каталоге пусто.
    catalog = (await client.get('/api/v1/olympiads')).json()
    assert 'Олимпиада Альфа' not in {o['name'] for o in catalog}

    confirmed = await client.post(f"/api/v1/imports/{doc['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['status'] == 'approved'

    catalog = (await client.get('/api/v1/olympiads')).json()
    alpha = next(o for o in catalog if o['name'] == 'Олимпиада Альфа')
    assert alpha['organizer_ids'] == [org['id']]
    assert alpha['levels'] == ['2']
    assert alpha['subjects'] == ['математика']
    beta = next(o for o in catalog if o['name'] == 'Олимпиада Бета')
    assert beta['subjects'] == ['физика', 'информатика']

    # Повторный confirm идемпотентен: approved допустим, дублей не создаёт.
    again = await client.post(f"/api/v1/imports/{doc['id']}/confirm")
    assert again.status_code == 200, again.text
    catalog = (await client.get('/api/v1/olympiads')).json()
    alphas = [o for o in catalog if o['name'] == 'Олимпиада Альфа']
    assert len(alphas) == 1


async def test_rsosh_import_reject_persists_nothing(client):
    org = await _setup_admin_and_org(client)
    uploaded = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Гамма', '', '')]),
    )
    doc = uploaded.json()

    from app.rsosh.processor import run_import

    section = await run_import(str(doc['id']))
    # Пустой уровень -> ревью.
    assert section['summary']['review'] == 1

    rejected = await client.post(f"/api/v1/imports/{doc['id']}/reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['status'] == 'rejected'

    catalog = (await client.get('/api/v1/olympiads')).json()
    assert 'Олимпиада Гамма' not in {o['name'] for o in catalog}


async def test_rsosh_import_merges_duplicate_into_existing(client):
    org = await _setup_admin_and_org(client)
    first = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Дельта', 'биология', '2')]),
    )
    from app.rsosh.processor import run_import

    await run_import(str(first.json()['id']))
    await client.post(f"/api/v1/imports/{first.json()['id']}/confirm")

    second = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'олимпиада дельта', 'биология', '3')]),
        name='second.xlsx',
    )
    section = await run_import(str(second.json()['id']))
    candidate = section['candidates'][0]
    assert candidate['action'] in ('merge', 'skip'), candidate

    confirmed = await client.post(
        f"/api/v1/imports/{second.json()['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text

    catalog = (await client.get('/api/v1/olympiads')).json()
    delta = next(o for o in catalog if 'дельта' in o['name'].lower())
    # Создано только ОДНО объединённое OLimpиада (не дубликат названия).
    deltas = [o for o in catalog if 'дельта' in o['name'].lower()]
    assert len(deltas) == 1
    assert delta['levels'] == ['2', '3']


async def test_import_requires_rsosh_list_document(client):
    org = await _setup_admin_and_org(client)
    doc = (
        await client.post(
            '/api/v1/docs',
            params={'type': 'OTHER', 'organization_id': org['id']},
            files={'file': ('note.pdf', b'%PDF fake', 'application/pdf')},
        )
    ).json()

    started = await client.post(
        '/api/v1/imports/rsosh',
        json={'doc_id': doc['id']},
    )
    assert started.status_code == 400


async def test_import_not_restartable_from_processed(client):
    org = await _setup_admin_and_org(client)
    uploaded = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Епсилон', 'астрономия', '1')]),
    )
    doc = uploaded.json()

    from app.rsosh.processor import run_import

    await run_import(str(doc['id']))
    await client.post(f"/api/v1/imports/{doc['id']}/confirm")

    with pytest.raises(ValueError):
        await run_import(str(doc['id']))


async def test_import_state_machine_via_http(client):
    """POST /imports/rsosh переводит документ в PROCESSING (async-запуск)."""
    org = await _setup_admin_and_org(client)
    uploaded = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Дзета', 'информатика', '2')]),
    )
    doc = uploaded.json()

    started = await client.post(
        '/api/v1/imports/rsosh',
        json={'doc_id': doc['id']},
    )
    assert started.status_code == 202, started.text
    assert started.json()['status'] == 'processing'

    status = (await client.get(f"/api/v1/imports/{doc['id']}")).json()
    assert status['status'] == 'processing'
    assert status['doc_status'] == 'PROCESSING'

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    assert preview.status_code == 409  # ещё processing (worker отсутствует)


async def test_import_list_for_admin(client):
    """GET /imports возвращает сводку по RSOSH-импортам загруженных списков."""
    org = await _setup_admin_and_org(client)
    first = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Йота', 'математика', '1')]),
        name='first.xlsx',
    )
    second = await _upload_list(
        client,
        org,
        _make_xlsx([('1', 'Олимпиада Каппа', 'физика', '3')]),
        name='second.xlsx',
    )
    other_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Другой оргкомитет', 'type': 'ORGANIZER'},
        )
    ).json()
    other = await _upload_list(
        client,
        other_org,
        _make_xlsx([('1', 'Олимпиада Лямбда', 'химия', '2')]),
        name='other.xlsx',
    )

    from app.rsosh.processor import run_import

    await run_import(str(first.json()['id']))
    await run_import(str(second.json()['id']))
    await run_import(str(other.json()['id']))

    listed = await client.get('/api/v1/imports')
    assert listed.status_code == 200, listed.text
    imports = listed.json()
    ids = {item['import_id'] for item in imports}
    # В тестовой БД остаются импорты других тестов сессии — проверяем
    # наличие своих (подмножество), а не точное равенство.
    assert {first.json()['id'], second.json()['id'], other.json()['id']} <= ids

    by_id = {item['import_id']: item for item in imports}
    item = by_id[first.json()['id']]
    assert item['state'] == 'review'
    assert item['summary']['new'] == 1
    assert item['doc_name'] == 'first.xlsx'

    # Орг-админ видит только импорты своей организации.
    member = await register_user(client)
    from tests.test_domain_api import _bind_org_admin

    await _bind_org_admin(client, member['id'], org['id'])
    listed2 = await client.get('/api/v1/imports')
    assert listed2.status_code == 200, listed2.text
    assert {item['import_id'] for item in listed2.json()} == {
        first.json()['id'],
        second.json()['id'],
    }