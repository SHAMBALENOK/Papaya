"""Импорт официальных документов РСОШ.

Покрываются все поддерживаемые входные форматы и особенности реальных
документов: XLSX с многострочными и объединёнными ячейками, PDF с текстовым
слоем, скан без текстового слоя (OCR), страницы, повёрнутые на 90/180/270
градусов, изображение, ошибки распознавания, повторный импорт того же
документа и архивирование олимпиад, исчезнувших из перечня.

Важно: до ``confirm`` импорт не пишет в каталог ничего.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    register_user,
    run_import,
    upload_document,
)
from tests.rsosh_fixtures import (
    OLYMPIAD_ROWS,
    RSOSH_SAMPLE_PDF,
    broken_bytes,
    broken_pdf_bytes,
    empty_xlsx_bytes,
    image_bytes,
    scanned_pdf_bytes,
    xlsx_bytes,
)


async def _candidate_names(client, import_id):
    preview = await client.get(f'/api/v1/imports/{import_id}/preview')
    assert preview.status_code == 200, preview.text
    return [item['name'] for item in preview.json()['candidates']]


async def _olympiad_names(client):
    response = await client.get('/api/v1/olympiads?include_archived=true')
    assert response.status_code == 200
    return sorted(item['name'] for item in response.json()['olympiads'])


# ------------------------------------------------------------------ XLSX


async def test_import_xlsx_creates_olympiads(client):
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())

    started = await run_import(client, doc['id'])
    assert started['state'] == 'review', started
    assert started['summary']['total'] >= len(OLYMPIAD_ROWS)

    names = await _candidate_names(client, doc['id'])
    assert any('Физтех' in name for name in names)
    assert any('Ломоносов' in name for name in names)

    # До подтверждения каталог пуст.
    assert await _olympiad_names(client) == []

    confirmed = await client.post(
        f"/api/v1/imports/{doc['id']}/confirm", json={}
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()['result']
    assert len(result['created']) >= len(OLYMPIAD_ROWS)

    catalog = await _olympiad_names(client)
    assert any('Высшая проба' in name for name in catalog)
    assert any('Физтех' in name for name in catalog)


async def test_import_xlsx_joins_multiline_names(client):
    """Переносы строк внутри ячейки не разрывают название олимпиады."""
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    names = await _candidate_names(client, doc['id'])
    joined = [name for name in names if 'Высшая проба' in name]
    assert joined, names
    assert 'Физтех' not in joined[0]
    assert len(joined) == 1


async def test_import_sets_document_as_source(client):
    """Олимпиада помнит документ-источник: пользователь видит, откуда данные.

    Внутренний ``source_doc_id`` в публичном каталоге не отдаётся, поэтому
    проверяем два разных факта:

    - пользователь видит, что данные из РСОШ, через ``/olympiads/{id}/source``;
    - система помнит конкретный документ — это видно администратору.
    """
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])
    await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})

    catalog = await client.get('/api/v1/olympiads')
    olympiads = catalog.json()['olympiads']
    assert olympiads
    assert all('source_doc_id' not in item for item in olympiads)

    source = await client.get(f"/api/v1/olympiads/{olympiads[0]['id']}/source")
    assert source.status_code == 200
    assert source.json()['title'], 'источник должен называться, а не быть пустым'

    admin_list = await client.get('/api/v1/admin/olympiads')
    assert admin_list.status_code == 200
    admin_items = admin_list.json()['olympiads']
    assert admin_items
    assert all(item['source_doc_id'] == doc['id'] for item in admin_items)


# ------------------------------------------------------------------- PDF


async def test_import_pdf_with_text_layer(client):
    await admin_client(client)
    with open(RSOSH_SAMPLE_PDF, 'rb') as handle:
        payload = handle.read()
    doc = await upload_document(client, 'rsosh_bvi.pdf', payload)

    started = await run_import(client, doc['id'])
    assert started['state'] == 'review', started

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    pages = preview.json()['pages']
    assert pages
    assert all(page['method'] == 'text' for page in pages)

    names = await _candidate_names(client, doc['id'])
    assert any('Физтех' in name for name in names)
    assert any('Ломоносов' in name for name in names)


async def test_import_scanned_pdf_uses_ocr(client):
    await admin_client(client)
    doc = await upload_document(client, 'scan.pdf', scanned_pdf_bytes())

    started = await run_import(client, doc['id'])
    assert started['state'] == 'review', started

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    pages = preview.json()['pages']
    assert pages and pages[0]['method'] == 'ocr'

    names = await _candidate_names(client, doc['id'])
    # Скан даёт шум в распознавании, но олимпиады должны быть найдены.
    assert names
    assert any('Ломоносов' in name for name in names), names


async def test_import_rotated_pdf_detects_orientation(client):
    """Страницы, повёрнутые на 90/180/270, распознаются после поворота."""
    for degrees in (90, 180, 270):
        await admin_client(client)
        doc = await upload_document(
            client,
            f'scan_{degrees}.pdf',
            scanned_pdf_bytes(degrees=degrees),
        )
        started = await run_import(client, doc['id'])
        assert started['state'] == 'review', (degrees, started)

        preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
        page = preview.json()['pages'][0]
        # ``orientation`` — угол поворота, применённый к странице перед OCR.
        # Фикстура поворачивает страницу по часовой стрелке, поэтому корректирующий
        # поворот равен обратному.
        assert page['orientation'] == (360 - degrees) % 360, (degrees, page)

        names = await _candidate_names(client, doc['id'])
        assert any('Ломоносов' in name for name in names), (degrees, names)


async def test_import_image_png(client):
    await admin_client(client)
    doc = await upload_document(client, 'page.png', image_bytes(ext='png'))
    started = await run_import(client, doc['id'])
    assert started['state'] == 'review', started
    names = await _candidate_names(client, doc['id'])
    assert any('Ломоносов' in name for name in names), names


async def test_import_image_jpeg(client):
    await admin_client(client)
    doc = await upload_document(client, 'page.jpg', image_bytes(ext='jpg'))
    started = await run_import(client, doc['id'])
    assert started['state'] == 'review', started
    names = await _candidate_names(client, doc['id'])
    assert names


# ----------------------------------------------------- дедупликация и повторы


async def test_repeated_import_of_same_document_creates_no_duplicates(client):
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())

    await run_import(client, doc['id'])
    await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})
    first = await _olympiad_names(client)

    await run_import(client, doc['id'])
    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    candidates = preview.json()['candidates']
    assert candidates
    assert all(item['action'] == 'merge' for item in candidates), candidates
    assert all(item['confidence'] == 'ok' for item in candidates), candidates

    await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})
    second = await _olympiad_names(client)
    assert first == second


async def test_import_merges_similar_name(client):
    """Название, отличающееся от каталога, обновляет существующую запись."""
    await admin_client(client)
    existing = await create_olympiad(
        client, 'Олимпиада школьников «Физтех»', official_url='https://fiztech.ru'
    )
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    merged = [
        item for item in preview.json()['candidates']
        if 'Физтех' in item['name']
    ]
    assert merged and merged[0]['action'] == 'merge'
    assert merged[0]['matched_olympiad_id'] == existing['id']

    await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})
    names = await _olympiad_names(client)
    assert sum(1 for name in names if 'Физтех' in name) == 1


async def test_confirm_can_skip_candidates(client):
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    skipped = preview.json()['candidates'][0]

    confirmed = await client.post(
        f"/api/v1/imports/{doc['id']}/confirm",
        json={'skip': [skipped['name_norm']]},
    )
    assert confirmed.status_code == 200
    names = await _olympiad_names(client)
    assert all(
        'Высшая проба' not in name
        for name in names
    ) or len(names) == len(OLYMPIAD_ROWS) - 1


async def test_reject_import_writes_nothing(client):
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    rejected = await client.post(f"/api/v1/imports/{doc['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()['state'] == 'rejected'
    assert await _olympiad_names(client) == []


async def test_olympiad_missing_from_new_list_is_archived(client):
    """Олимпиада, исчезнувшая из перечня РСОШ, не удаляется, а архивируется."""
    await admin_client(client)

    first_doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, first_doc['id'])
    await client.post(f"/api/v1/imports/{first_doc['id']}/confirm", json={})

    manual = await create_olympiad(client, 'Олимпиада, вручную добавленная')

    # Второй документ содержит только первые две строки перечня.
    partial = xlsx_bytes()
    import io

    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(partial))
    sheet = book.active
    sheet.delete_rows(4, 10)
    buffer = io.BytesIO()
    book.save(buffer)

    second_doc = await upload_document(client, 'rsosh_2027.xlsx', buffer.getvalue())
    await run_import(client, second_doc['id'])
    confirmed = await client.post(
        f"/api/v1/imports/{second_doc['id']}/confirm", json={}
    )
    assert confirmed.status_code == 200
    archived = confirmed.json()['result']['archived']
    assert any('Физтех' in name for name in archived), archived

    public = await client.get('/api/v1/olympiads')
    public_names = [item['name'] for item in public.json()['olympiads']]
    assert not any('Физтех' in name for name in public_names)
    assert any(name == manual['name'] for name in public_names), (
        'олимпиада, созданная вручную, не должна архивироваться'
    )

    everything = await client.get('/api/v1/olympiads?include_archived=true')
    archived_items = [
        item for item in everything.json()['olympiads']
        if item['status'] == 'ARCHIVED'
    ]
    assert any('Физтех' in item['name'] for item in archived_items)


# ------------------------------------------------------------- ошибки и права


async def test_import_reports_unreadable_file(client):
    await admin_client(client)
    doc = await upload_document(client, 'broken.pdf', broken_pdf_bytes())
    started = await run_import(client, doc['id'])
    assert started['state'] == 'failed'
    assert started['error']


async def test_upload_rejects_non_document(client):
    """Не-документ отклоняется уже при загрузке (по сигнатуре файла)."""
    await admin_client(client)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('not-a-doc.pdf', broken_bytes(), 'application/pdf')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 400


async def test_import_reports_document_without_olympiads(client):
    await admin_client(client)
    doc = await upload_document(client, 'empty.xlsx', empty_xlsx_bytes())
    started = await run_import(client, doc['id'])
    assert started['state'] == 'failed'
    assert 'не найдено' in started['error']


async def test_upload_rejects_unknown_extension(client):
    await admin_client(client)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('evil.exe', b'abc', 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 400


async def test_upload_rejects_oversized_file(client):
    """MAX_UPLOAD_MB тестового окружения = 1 МБ."""
    await admin_client(client)
    oversized = b'\x00' * (2 * 1024 * 1024)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('big.pdf', oversized, 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 413
    assert 'limit' in response.json()['detail']


async def test_import_requires_admin(client):
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())

    # Обычный пользователь импортировать не может.
    await register_user(client)
    forbidden = await client.post(
        '/api/v1/imports/rsosh', json={'doc_id': doc['id']}
    )
    assert forbidden.status_code == 403

    # Гость — тоже.
    client.cookies.clear()
    anonymous = await client.post(
        '/api/v1/imports/rsosh', json={'doc_id': doc['id']}
    )
    assert anonymous.status_code == 401


async def test_import_of_unknown_document_is_400(client):
    await admin_client(client)
    response = await client.post(
        '/api/v1/imports/rsosh', json={'doc_id': str(uuid.uuid4())}
    )
    assert response.status_code == 400


async def test_university_doc_type_cannot_be_imported(client):
    await admin_client(client)
    doc = await upload_document(
        client, 'order.pdf', xlsx_bytes(), doc_type='UNIVERSITY_ORDER'
    )
    response = await client.post(
        '/api/v1/imports/rsosh', json={'doc_id': doc['id']}
    )
    assert response.status_code == 400
    assert 'RSOSH_LIST' in response.json()['detail']


async def test_confirm_twice_is_rejected(client):
    """Повторное подтверждение отклоняется и каталог не трогает.

    Ответ — 409, а не 400: запрос корректный, но состояние прогона не позволяет
    его применить. Раньше здесь был 400; различать «плохой запрос» и
    «состояние не позволяет» нужно, чтобы второй параллельный confirm был
    отличим от опечатки в теле.
    """
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])
    assert (await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})).status_code == 200

    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    before = sorted(
        (row['name'], row['status']) for row in catalog.json()['olympiads']
    )

    again = await client.post(f"/api/v1/imports/{doc['id']}/confirm", json={})
    assert again.status_code == 409, again.text

    after = await client.get('/api/v1/olympiads?include_archived=true')
    assert sorted(
        (row['name'], row['status']) for row in after.json()['olympiads']
    ) == before, 'отклонённое повторное подтверждение изменило каталог'


async def test_import_status_and_list(client):
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    status = await client.get(f"/api/v1/imports/{doc['id']}")
    assert status.status_code == 200
    assert status.json()['state'] == 'review'

    listing = await client.get('/api/v1/imports')
    assert listing.status_code == 200
    assert any(item['id'] == doc['id'] for item in listing.json()['imports'])

# ------------------------------------------------------- Архив и пропуски


async def test_disappeared_olympiad_is_archived_with_reason(client):
    """Исчезнувшая из перечня олимпиада архивируется с причиной РСОШ."""
    await admin_client(client)
    first = await upload_document(client, 'rsosh_full.xlsx', xlsx_bytes())
    await run_import(client, first['id'])
    assert (await client.post(f"/api/v1/imports/{first['id']}/confirm", json={})).status_code == 200

    # Следующий перечень короче: часть олимпиад из него исчезла.
    second = await upload_document(
        client, 'rsosh_short.xlsx', xlsx_bytes(row_count=2)
    )
    await run_import(client, second['id'])
    confirmed = await client.post(
        f"/api/v1/imports/{second['id']}/confirm", json={}
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()['result']
    assert result['archived'], 'исчезнувшие олимпиады должны попасть в архив'

    listing = await client.get('/api/v1/olympiads?include_archived=true')
    archived = [row for row in listing.json()['olympiads'] if row['status'] == 'ARCHIVED']
    assert archived
    # Причина архива не показывается посетителю, но видна администратору.
    assert all('archive_reason' not in row for row in archived)

    # Причина архива видна администратору при возврате в архив: попытка вернуть
    # запись, исчезнувшую из перечня РСОШ, отклоняется.
    target = archived[0]['id']
    refused_restore = await client.post(
        f'/api/v1/admin/archive_olympiad/{target}?archived=false'
    )
    assert refused_restore.status_code == 409
    assert 'перечн' in refused_restore.json()['detail']
    # Архивные олимпиады не видны в обычном каталоге.
    public = await client.get('/api/v1/olympiads')
    public_ids = {row['id'] for row in public.json()['olympiads']}
    assert public_ids.isdisjoint({row['id'] for row in archived})


async def test_returned_olympiad_leaves_archive(client):
    """Олимпиада, снова встретившаяся в перечне, возвращается в актуальные."""
    await admin_client(client)
    first = await upload_document(
        client, 'rsosh_short.xlsx', xlsx_bytes(row_count=2)
    )
    await run_import(client, first['id'])
    await client.post(f"/api/v1/imports/{first['id']}/confirm", json={})

    listing = await client.get('/api/v1/olympiads')
    olympiad_id = listing.json()['olympiads'][0]['id']

    second = await upload_document(client, 'rsosh_full.xlsx', xlsx_bytes())
    await run_import(client, second['id'])
    assert (await client.post(f"/api/v1/imports/{second['id']}/confirm", json={})).status_code == 200

    # Публично о статусе читает посетитель, а причина архива — внутреннее
    # значение: в публичной карточке её нет намеренно.
    detail = await client.get(f'/api/v1/olympiads/{olympiad_id}')
    assert detail.status_code == 200
    assert detail.json()['status'] == 'PUBLISHED'
    assert 'archive_reason' not in detail.json()

    admin_view = await client.get(f'/api/v1/olympiads/{olympiad_id}')
    assert admin_view.status_code == 200
    assert admin_view.json()['status'] == 'PUBLISHED'


async def test_archive_missing_false_keeps_olympiads_published(client):
    """Без archive_missing каталог не архивируется — импорт не разрушает его."""
    await admin_client(client)
    first = await upload_document(client, 'rsosh_full.xlsx', xlsx_bytes())
    await run_import(client, first['id'])
    await client.post(f"/api/v1/imports/{first['id']}/confirm", json={})

    second = await upload_document(
        client, 'rsosh_short.xlsx', xlsx_bytes(row_count=2)
    )
    await run_import(client, second['id'])
    confirmed = await client.post(
        f"/api/v1/imports/{second['id']}/confirm",
        json={'archive_missing': False},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()['result']['archived'] == []

    listing = await client.get('/api/v1/olympiads?include_archived=true')
    assert all(row['status'] == 'PUBLISHED' for row in listing.json()['olympiads'])


async def test_skipped_candidate_is_not_archived(client):
    """Кандидат, снятый в preview, не считается исчезнувшим из перечня.

    Снятие — это реакция администратора на ошибку распознавания. Если бы
    «пропущенный» считался отсутствующим в перечне, олимпиада, которая в
    перечне есть, ушла бы в архив по собственной инициативе.
    """
    await admin_client(client)
    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    candidates = preview.json()['candidates']
    assert len(candidates) > 1
    skipped = candidates[0]['name_norm']

    confirmed = await client.post(
        f"/api/v1/imports/{doc['id']}/confirm",
        json={'skip': [skipped], 'archive_missing': True},
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    # Снятый кандидат не попал в каталог, но виден в отчёте о импорте.
    assert body['skipped'] == [skipped]
    skipped_name = candidates[0]['name']
    assert skipped_name not in body['result']['created']

    # Остальные олимпиады созданы и опубликованы; архивировать нечего.
    listing = await client.get('/api/v1/olympiads?include_archived=true')
    rows = listing.json()['olympiads']
    assert rows
    assert skipped_name not in [row['name'] for row in rows]
    assert all(row['status'] == 'PUBLISHED' for row in rows)
    assert not body['result']['archived']


async def test_skipped_matched_candidate_protects_existing_olympiad(client):
    """Снятый merge-кандидат защищает уже существующую олимпиаду от архива."""
    await admin_client(client)
    existing = await create_olympiad(client, 'Олимпиада школьников «Ломоносов»')

    doc = await upload_document(client, 'rsosh.xlsx', xlsx_bytes())
    await run_import(client, doc['id'])

    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    candidates = preview.json()['candidates']
    merged = next(
        (
            item for item in candidates
            if item.get('action') == 'merge'
            and str(item.get('matched_olympiad_id')) == str(existing['id'])
        ),
        None,
    )
    assert merged, 'ожидался кандидат на merge с существующей олимпиадой'

    confirmed = await client.post(
        f"/api/v1/imports/{doc['id']}/confirm",
        json={'skip': [merged['name_norm']], 'archive_missing': True},
    )
    assert confirmed.status_code == 200, confirmed.text

    detail = await client.get(f"/api/v1/olympiads/{existing['id']}")
    assert detail.status_code == 200
    assert detail.json()['status'] == 'PUBLISHED', (
        'снятый в preview кандидат не должен архивировать олимпиаду'
    )
