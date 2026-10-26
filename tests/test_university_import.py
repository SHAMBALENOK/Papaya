"""Импорт приказа университета: preview без записи, confirm без автоподтверждения.

Проверяется главный инвариант вузовского адаптера, отличающий его от импорта
РСОШ: приказ **не создаёт олимпиад** и **не публикует правила**. До ``confirm``
каталог и правила пусты; после ``confirm`` появляются только черновики правил
(``draft``) по уже существующим олимпиадам, и публикует/проверяет их человек,
а не импорт.

Тесты идут через API загрузки документа (он же проверяет тип) и напрямую через
``app.university.processor``/``persist``: HTTP-роуты импорта приказа —
отдельный шаг, а проверять нужно именно ядро адаптера.
"""

from pathlib import Path

import pytest

from app.university import processor
from app.university.types import UniversityError
from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    upload_document,
)

REAL_ORDER_PDF = (
    Path(__file__).resolve().parents[1]
    / 'app'
    / 'tables'
    / 'rsosh_bvi'
    / 'rsosh_bvi.pdf'
)


async def _stored_links(university_id: str, olympiad_id: str) -> dict | None:
    """Правило льготы для пары напрямую из БД (в обход API)."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from app.database.database import AsyncSessionLocal
    from app.models.benefit_rules import BenefitRule

    async with AsyncSessionLocal() as session:
        link = (
            await session.execute(
                select(BenefitRule)
                .where(
                    BenefitRule.university_id == uuid_mod.UUID(str(university_id)),
                    BenefitRule.olympiad_id == uuid_mod.UUID(str(olympiad_id)),
                )
                .order_by(BenefitRule.createdAt)
            )
        ).scalars().first()
        if link is None:
            return None
        return {
            'id': link.id,
            'status': link.status,
            'source_doc_id': link.source_doc_id,
            'source_meta': link.source_meta,
        }


async def test_import_order_preview_creates_no_links(client):
    """Preview строит кандидатов, но не создаёт ни олимпиад, ни связей."""
    await admin_client(client)
    university = await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Всероссийская олимпиада школьников «Высшая проба»'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )

    result, _mode = await processor.start_import(doc['id'])
    section = result['metadata']['university']
    assert section['state'] == 'review', section
    assert section['university']['name'] == 'Университет ИТМО'

    # До подтверждения связи не создаются: приказ ничего не пишет сам.
    link = await _stored_links(university['id'], olympiad['id'])
    assert link is None

    names = {c['olympiad_name'] for c in section['candidates']}
    assert 'Всероссийская олимпиада школьников «Высшая проба»' in names


async def test_confirm_creates_draft_rules_only(client):
    """Confirm создаёт только черновики правил по существующим олимпиадам.

    Олимпиада, которой не было в каталоге, приказом не создаётся: такие строки
    остаются несопоставленными и требуют ручного связывания.
    """
    await admin_client(client)
    university = await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Всероссийская олимпиада школьников «Высшая проба»'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    before = await client.get('/api/v1/olympiads?include_archived=true')
    before_count = len(before.json()['olympiads'])

    await processor.start_import(doc['id'])
    applied = await processor.confirm_import(doc['id'])

    assert applied['result']['linked'] >= 1
    assert applied['result']['unmatched'] >= 1

    link = await _stored_links(university['id'], olympiad['id'])
    assert link is not None
    assert link['status'] == 'draft'
    assert str(link['source_doc_id']) == str(doc['id'])
    assert link['source_meta'].get('olympiad_name')

    # Каталог олимпиад не изменился: приказ не создаёт олимпиад.
    after = await client.get('/api/v1/olympiads?include_archived=true')
    assert len(after.json()['olympiads']) == before_count

    state = applied['document']['metadata']['university']
    assert state['state'] == 'approved'


async def test_confirm_records_source_provenance(client):
    """Связь хранит документ-источник и распознанные характеристики строки."""
    await admin_client(client)
    await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Московская олимпиада школьников'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    await processor.start_import(doc['id'])
    await processor.confirm_import(doc['id'])

    university_id = (
        await client.get('/api/v1/universities?limit=1')
    ).json()['universities'][0]['id']
    link = await _stored_links(university_id, olympiad['id'])
    assert link is not None
    meta = link['source_meta']
    assert meta['olympiad_name'] == 'Московская олимпиада школьников'
    assert 'directions' in meta or 'direction' in meta


async def test_confirm_is_idempotent(client):
    """Повторный confirm не создаёт второе правило: черновик дополняется."""
    await admin_client(client)
    await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Всероссийская олимпиада школьников «Высшая проба»'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    await processor.start_import(doc['id'])
    await processor.confirm_import(doc['id'])

    # Повторный импорт того же документа обрабатывается заново, но связь одна.
    await processor.start_import(doc['id'])
    await processor.confirm_import(doc['id'])

    import uuid as uuid_mod

    from sqlalchemy import func, select

    from app.database.database import AsyncSessionLocal
    from app.models.benefit_rules import BenefitRule

    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(BenefitRule).where(
                    BenefitRule.olympiad_id == uuid_mod.UUID(olympiad['id'])
                )
            )
        ).scalar_one()
    assert count == 1


async def test_confirm_rejects_unmatched_without_selection(client):
    """Без университета приказ подтвердить нельзя: связи некуда привязать."""
    await admin_client(client)
    await create_olympiad(client, name='Московская олимпиада школьников')
    # Университет не создан, в шапке он распознан, но в каталоге его нет.
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    await processor.start_import(doc['id'])

    with pytest.raises(UniversityError):
        await processor.confirm_import(doc['id'])


async def test_reject_keeps_catalog_untouched(client):
    """Отклонение выставляет состояние и не трогает ни каталог, ни связи."""
    from app.university import persist

    await admin_client(client)
    university = await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Всероссийская олимпиада школьников «Высшая проба»'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    await processor.start_import(doc['id'])
    rejected = await persist.reject_import(doc['id'])
    assert rejected['metadata']['university']['state'] == 'rejected'
    assert await _stored_links(university['id'], olympiad['id']) is None


async def test_wrong_document_type_is_not_importable(client):
    """Документ РСОШ нельзя импортировать вузовским адаптером."""
    from tests.rsosh_fixtures import xlsx_bytes

    await admin_client(client)
    doc = await upload_document(
        client, 'rsosh.xlsx', xlsx_bytes(), doc_type='RSOSH_LIST'
    )
    with pytest.raises(UniversityError):
        await processor.start_import(doc['id'])


# ------------------------------------------------------------------ HTTP-роуты


async def _start_university_import(client, doc_id):
    response = await client.post(
        '/api/v1/imports/university', json={'doc_id': doc_id}
    )
    assert response.status_code == 202, response.text
    return response.json()


async def test_university_routes_full_cycle(client):
    """Сквозной путь через HTTP: старт → preview → selection → confirm.

    Проверяется, что роуты приказа отделены от роутов РСОШ и повторяют тот же
    контракт: preview не пишет, confirm создаёт заявки, выбор сохраняется.
    """
    await admin_client(client)
    university = await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Всероссийская олимпиада школьников «Высшая проба»'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )

    started = await _start_university_import(client, doc['id'])
    assert started['state'] == 'review', started

    listed = await client.get('/api/v1/imports/university')
    assert listed.status_code == 200, listed.text
    assert any(item['id'] == doc['id'] for item in listed.json()['imports'])

    status = await client.get(f"/api/v1/imports/university/{doc['id']}")
    assert status.status_code == 200
    assert status.json()['state'] == 'review'

    preview = await client.get(f"/api/v1/imports/university/{doc['id']}/preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body['university']['name'] == 'Университет ИТМО'
    names = {c['olympiad_name'] for c in body['candidates']}
    assert 'Всероссийская олимпиада школьников «Высшая проба»' in names

    # До подтверждения связей нет.
    assert await _stored_links(university['id'], olympiad['id']) is None

    confirmed = await client.post(
        f"/api/v1/imports/university/{doc['id']}/confirm", json={}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['result']['linked'] >= 1

    link = await _stored_links(university['id'], olympiad['id'])
    assert link is not None and link['status'] == 'draft'


async def test_university_preview_rejects_rsosh_document(client):
    """Роут приказа не отдаёт прогон РСОШ: типы документов разделены."""
    from tests.rsosh_fixtures import xlsx_bytes

    await admin_client(client)
    doc = await upload_document(
        client, 'rsosh.xlsx', xlsx_bytes(), doc_type='RSOSH_LIST'
    )
    response = await client.get(
        f"/api/v1/imports/university/{doc['id']}/preview"
    )
    assert response.status_code == 404


async def test_university_reject_route(client):
    """Отклонение через HTTP выставляет состояние и не пишет связи."""
    await admin_client(client)
    university = await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Московская олимпиада школьников'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    await _start_university_import(client, doc['id'])

    rejected = await client.post(
        f"/api/v1/imports/university/{doc['id']}/reject"
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['state'] == 'rejected'
    assert await _stored_links(university['id'], olympiad['id']) is None


async def test_university_selection_route_saves_choice(client):
    """Выбор администратора (ручная связь несопоставленной строки) сохраняется."""
    await admin_client(client)
    university = await create_university(client, name='Университет ИТМО')
    olympiad = await create_olympiad(
        client, name='Всероссийская олимпиада школьников «Высшая проба»'
    )
    doc = await upload_document(
        client,
        'order.pdf',
        REAL_ORDER_PDF.read_bytes(),
        doc_type='UNIVERSITY_ORDER',
        name='Приказ ИТМО',
    )
    await _start_university_import(client, doc['id'])

    preview = await client.get(f"/api/v1/imports/university/{doc['id']}/preview")
    candidates = preview.json()['candidates']
    unmatched = next(c for c in candidates if not c['olympiad_id'])
    unmatched_before = sum(1 for c in candidates if not c['olympiad_id'])

    saved = await client.put(
        f"/api/v1/imports/university/{doc['id']}/selection",
        json={'links': {unmatched['name_norm']: olympiad['id']}},
    )
    assert saved.status_code == 200, saved.text

    # Подтверждение без тела использует сохранённый выбор: несопоставленная
    # строка получает связь, а университет берётся из шапки документа.
    confirmed = await client.post(
        f"/api/v1/imports/university/{doc['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()['result']
    assert result['unmatched'] == unmatched_before - 1
    assert await _stored_links(university['id'], olympiad['id']) is not None
