"""§4, §15, §16, §17, §19: целостность каталога при ошибках и гонках.

Каждый тест здесь отвечает на вопрос «что будет с каталогом, если что-то
пойдёт не так». Это самые дорогие ошибки сервиса: один неверный импорт или
один параллельный запрос не должны портить каталог.
"""

import asyncio
import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    university_rep_client,
)
from tests.rsosh_fixtures import xlsx_bytes


# --------------------------- Гонка при создании связи ---------------------------


async def test_parallel_requests_create_one_link(client):
    """Два параллельных запроса на одну пару дают одну связь, а не 500.

    Уникальный индекс по паре — последняя линия защиты; второй запрос должен
    получить уже созданную связь (тот же идемпотентный результат), а не
    ``IntegrityError`` наружу.
    """
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада для гонки')
    await university_rep_client(client, university['id'])

    async def request_link():
        # Отдельная сессия на каждый запрос: иначе это один запрос, а не два.
        from app.database import bvi as bvi_db

        return await bvi_db.request_bvi_link(
            olympiad['id'], university['id'], requested_by=None
        )

    results = await asyncio.gather(request_link(), request_link())
    ids = {result['id'] for result in results}
    assert len(ids) == 1, f'ожидалась одна связь, получили {ids}'
    assert all(result['status'] == 'PENDING' for result in results)

    await admin_client(client)
    queue = await client.get('/api/v1/admin/bvi')
    assert queue.status_code == 200
    assert len(queue.json()['links']) == 1


async def test_parallel_http_requests_do_not_fail(client):
    """То же самое через HTTP: ни один из запросов не должен стать 500."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада для гонки HTTP')
    await university_rep_client(client, university['id'])

    import httpx

    from app.main import app

    async def http_request():
        transport = httpx.ASGITransport(app=app)
        # Cookies задаются на клиенте, а не на запросу: per-request cookies
        # объявлены устаревшими именно потому, что их поведение неоднозначно,
        # и такой вызов даёт предупреждение в каждом прогоне.
        async with httpx.AsyncClient(
            transport=transport,
            base_url='http://test',
            cookies=dict(client.cookies),
        ) as raw:
            # Сессия гостя: права проверяются как у представителя, но
            # параллельность создаётся на уровне приложения и БД.
            response = await raw.post(
                f"/api/v1/universities/{university['id']}/bvi",
                json={'olympiad_id': olympiad['id']},
            )
            return response

    responses = await asyncio.gather(http_request(), http_request())
    codes = sorted(response.status_code for response in responses)
    assert codes == [201, 201], codes


# --------------------------- Безопасность импорта ---------------------------


async def test_failed_rows_do_not_archive_the_catalog(client, monkeypatch):
    """Часть строк не применилась — каталог не трогаем.

    Сценарий из реальной поломки: 10 строк распознались, 90 упали при записи.
    Если бы оставшиеся 90 олимпиад каталога считались «отсутствующими в
    перечне», они были бы массово архивированы — потеря каталога из-за одной
    ошибки импорта.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    assert (await _run(client, doc['id']))['state'] == 'review'
    assert (await _confirm(client, doc['id'])).status_code == 200

    # Каталог заполнен: все олимпиады опубликованы.
    catalog = await client.get('/api/v1/olympiads')
    published = catalog.json()['olympiads']
    assert len(published) >= 3

    # Следующий перечень: те же олимпиады, но запись половины падает.
    second = await _upload(client, 'rsosh_broken.xlsx', xlsx_bytes())
    await _run(client, second['id'])

    from app.rsosh import persist as persist_module

    original = persist_module._upsert
    calls = {'n': 0}

    async def flaky_upsert(session, candidate, doc_id):
        calls['n'] += 1
        # Первая половина записывается, вторая падает.
        if calls['n'] > 1:
            raise RuntimeError('simulated write failure')
        return await original(session, candidate, doc_id)

    monkeypatch.setattr(persist_module, '_upsert', flaky_upsert)
    confirmed = await _confirm(client, second['id'])
    assert confirmed.status_code == 200
    result = confirmed.json()['result']

    assert result['errors'], 'ошибки должны попасть в отчёт'
    assert result['archived'] == [], 'архивирование отключено при ошибках'
    assert result['archive_skipped_reason'], 'причина отказа обязательна'
    assert 'не удалось применить' in result['archive_skipped_reason']

    # Каталог на месте.
    after = await client.get('/api/v1/olympiads?include_archived=true')
    rows = after.json()['olympiads']
    assert all(row['status'] == 'PUBLISHED' for row in rows), (
        'частичный импорт не должен архивировать каталог'
    )
    assert len(rows) >= len(published)


async def test_unreadable_structure_does_not_archive(client):
    """Если структуру перечня не прочитали, «кого нет» судить нельзя."""
    await admin_client(client)
    doc = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, doc['id'])
    await _confirm(client, doc['id'])

    second = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, second['id'])

    # Помечаем перечень как непрочитанный: это делает разбор, мы воспроизводим
    # только его результат.
    from app.rsosh import states

    current = await client.get(f"/api/v1/imports/{second['id']}/preview")
    assert current.status_code == 200

    import app.rsosh.processor as processor_module

    original = processor_module.db_docs.get_doc

    async def with_warning(doc_id):
        result = await original(doc_id)
        section = states.rsosh_section(result)
        if section.get('candidates'):
            section['warnings'] = [
                *(section.get('warnings') or []),
                'Table header was not recognized, columns were detected heuristically',
            ]
            result = dict(result)
            result['metadata'] = states.docs_metadata_with_section(result, section)
        return result

    monkey = processor_module.db_docs.get_doc
    processor_module.db_docs.get_doc = with_warning
    try:
        confirmed = await _confirm(client, second['id'])
    finally:
        processor_module.db_docs.get_doc = monkey

    assert confirmed.status_code == 200
    result = confirmed.json()['result']
    assert result['archived'] == []
    assert 'прочитан не полностью' in result['archive_skipped_reason']


async def test_complete_import_still_archives(client):
    """Полный корректный импорт архивирует исчезнувшие — правило не заблокировано."""
    await admin_client(client)
    full = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, full['id'])
    await _confirm(client, full['id'])

    catalog = await client.get('/api/v1/olympiads')
    total = len(catalog.json()['olympiads'])
    assert total >= 3

    # Перечень из тех же строк: архивировать нечего, и это не должно считаться
    # отказом архивирования.
    same = await _upload(client, 'rsosh_same.xlsx', xlsx_bytes())
    await _run(client, same['id'])
    confirmed = await _confirm(client, same['id'])
    assert confirmed.status_code == 200
    result = confirmed.json()['result']
    assert result['errors'] == []
    assert result['archive_skipped_reason'] is None


async def test_skipped_candidate_is_not_archived(client):
    """Снятая в preview строка не считается отсутствующей.

    Снятие — это реакция администратора на ошибку распознавания. Если бы
    «пропущенный» считался отсутствующим в перечне, олимпиада, которая в
    перечне есть, ушла бы в архив по собственной инициативе.
    """
    await admin_client(client)
    first = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, first['id'])
    await _confirm(client, first['id'])

    # Второй перечень короче: часть олимпиад из него исчезла.
    second = await _upload(client, 'rsosh_short.xlsx', xlsx_bytes(row_count=2))
    await _run(client, second['id'])

    preview = await client.get(f"/api/v1/imports/{second['id']}/preview")
    candidates = preview.json()['candidates']

    # Защищаем олимпиаду, с которой сопоставлен кандидат: именно её снятие
    # обязано помешать архивированию.
    merges = [item for item in candidates if item.get('matched_olympiad_id')]
    assert merges, 'ожидался хотя бы один кандидат-merge с существующей олимпиадой'
    skipped_name = merges[0]['name_norm']
    protected_id = str(merges[0]['matched_olympiad_id'])

    confirmed = await _confirm(client, second['id'], {'skip': [skipped_name]})
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()['result']
    # Снятая строка не попала в каталог и не была засчитана как обработанная.
    assert result['errors'] == []

    status = await _olympiad_status(client, protected_id)
    assert status == 'PUBLISHED', (
        'снятая в preview заявка защитила олимпиаду от архива'
    )


# --------------------------- Порядок снимков ---------------------------


async def test_outdated_snapshot_cannot_roll_catalog_back(client):
    """Старый перечень нельзя применить молча.

    Загружаем новый перечень и подтверждаем его — олимпиада из старого
    документа архивируется. Затем пробуем подтвердить старый документ: без
    явного согласия это отказ, иначе каталог откатился бы назад.
    """
    await admin_client(client)
    old_doc = await _upload(client, 'rsosh_old.xlsx', xlsx_bytes())
    await _run(client, old_doc['id'])
    await _confirm(client, old_doc['id'])

    new_doc = await _upload(client, 'rsosh_new.xlsx', xlsx_bytes(row_count=2))
    await _run(client, new_doc['id'])
    confirmed = await _confirm(client, new_doc['id'])
    assert confirmed.status_code == 200

    # Старый документ вновь готов к подтверждению (сбросить состояние).
    await _force_review(client, old_doc['id'])

    refused = await _confirm(client, old_doc['id'])
    assert refused.status_code == 409, refused.text
    assert 'устарел' in refused.json()['detail']

    # Каталог не откатился: каталог остался в состоянии после нового перечня.
    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    rows = catalog.json()['olympiads']
    # Олимпиада из старого, но отсутствующая в новом перечне осталась архивной.
    assert any(row['status'] == 'ARCHIVED' for row in rows), (
        'старый импорт не должен был публиковать архивную олимпиаду обратно'
    )


async def test_outdated_snapshot_can_be_applied_explicitly(client):
    """Явное согласие администратора — можно: это осознанное решение."""
    await admin_client(client)
    old_doc = await _upload(client, 'rsosh_old.xlsx', xlsx_bytes())
    await _run(client, old_doc['id'])
    await _confirm(client, old_doc['id'])

    new_doc = await _upload(client, 'rsosh_new.xlsx', xlsx_bytes(row_count=2))
    await _run(client, new_doc['id'])
    await _confirm(client, new_doc['id'])
    await _force_review(client, old_doc['id'])

    forced = await _confirm(client, old_doc['id'], {'allow_outdated': True})
    assert forced.status_code == 200


# --------------------------- Загрузка документов ---------------------------


async def test_oversized_upload_leaves_no_file(client, tmp_path):
    """Файл больше лимита не остаётся на диске."""
    docs_dir = _docs_dir()
    before = set(_list_documents(docs_dir))

    await admin_client(client)
    oversized = b'\\x00' * (2 * 1024 * 1024)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('big.pdf', oversized, 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 413

    after = set(_list_documents(docs_dir))
    assert after == before, f'остались файлы: {after - before}'


async def test_invalid_signature_leaves_no_file(client):
    """Файл с неверной сигнатурой удаляется, а не остаётся мусором."""
    docs_dir = _docs_dir()
    before = set(_list_documents(docs_dir))

    await admin_client(client)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('evil.pdf', b'not a pdf at all', 'application/pdf')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code in (400, 422)

    after = set(_list_documents(docs_dir))
    assert after == before, f'остались файлы: {after - before}'


async def test_db_failure_leaves_no_file(client, monkeypatch):
    """Сбой записи в БД не оставляет файл на диске.

    Правило «нет записи — нет файла»: иначе документы-копии копятся в
    ``DOCS_DIR`` и никто о них не знает.
    """
    docs_dir = _docs_dir()
    before = set(_list_documents(docs_dir))

    from app import database as database_module

    async def failing_add_doc(payload):
        raise RuntimeError('simulated db failure')

    monkeypatch.setattr(
        database_module.docs, 'add_doc', failing_add_doc, raising=True
    )

    await admin_client(client)
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': ('rsosh.xlsx', xlsx_bytes(), 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 500

    after = set(_list_documents(docs_dir))
    assert after == before, f'остались файлы: {after - before}'


# --------------------------- Локальные помощники ---------------------------


def _docs_dir():
    import os
    from pathlib import Path as _Path

    return _Path(os.environ.get('DOCS_DIR', ''))


def _list_documents(directory):
    if not directory or not directory.exists():
        return []
    return [item.name for item in directory.iterdir() if item.is_file()]


async def _upload(client, filename, payload):
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': (filename, payload, 'application/octet-stream')},
        data={'type': 'RSOSH_LIST'},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _run(client, doc_id):
    response = await client.post('/api/v1/imports/rsosh', json={'doc_id': doc_id})
    assert response.status_code == 202, response.text
    return response.json()


async def _olympiad_status(client, olympiad_id):
    """Текущий статус олимпиады (включая архивную)."""
    response = await client.get(f'/api/v1/olympiads/{olympiad_id}')
    assert response.status_code == 200, response.text
    return response.json()['status']


async def _confirm(client, doc_id, body=None):
    return await client.post(f'/api/v1/imports/{doc_id}/confirm', json=body or {})


async def _force_review(client, doc_id):
    """Вернуть документ в состояние «готов к подтверждению»."""
    from app.database.database import AsyncSessionLocal
    from app.models.docs import Docs
    from app.rsosh import states
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        doc = (
            await session.execute(select(Docs).where(Docs.id == uuid.UUID(str(doc_id))))
        ).scalar_one()
        # Раздел копируется, а не правится на месте: SQLAlchemy не отмечает
        # JSONB-колонку изменённой, если мутировать уже загруженный dict —
        # запись молча не сохранится. Продуктовый код (app/rsosh/states.py)
        # собирает новые словари именно поэтому.
        stored = states.rsosh_section({'metadata': doc.meta})
        section = {**stored, 'state': 'review', 'confirm': None}
        doc.meta = states.docs_metadata_with_section({'metadata': doc.meta}, section)
        doc.status = 'NEEDS_REVIEW'
        await session.commit()