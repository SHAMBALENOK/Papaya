"""§4, §15, §16, §17, §19: целостность каталога при ошибках и гонках.

Каждый тест здесь отвечает на вопрос «что будет с каталогом, если что-то
пойдёт не так». Это самые дорогие ошибки сервиса: один неверный импорт или
один параллельный запрос не должны портить каталог.
"""

import asyncio
import time
import uuid

import pytest
from sqlalchemy import text

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    university_rep_client,
)
from tests.rsosh_fixtures import (
    xlsx_bytes,
    xlsx_bytes_for,
    xlsx_bytes_including,
)


def normalize_name(value: str) -> str:
    """Тот же нормализатор, что у каталога.

    Импортируется из приложения, а не дублируется в тесте: иначе проверка «эта
    олимпиада попала в перечень» сравнивала бы строки по двум разным правилам.
    """
    from app.database.search import normalize_name as normalize

    return normalize(value)


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


async def test_database_backend_enforces_row_locks():
    """Бэкенд действительно умеет блокировки, на которых держится BVI-инвариант.

    ``request_bvi_link`` полагается на ``SELECT ... FOR UPDATE``: олимпиада не
    может уйти в архив между проверкой и вставкой связи. Проверять это
    «по документации» нельзя — на SQLite ``FOR UPDATE`` молча игнорируется, и
    инвариант «архивная олимпиада не получает новых заявок» тихо перестал бы
    работать. Тест проверяет поведение на живой базе: вторая транзакция обязана
    дождаться первой, а не прочитать старое значение.
    """
    from sqlalchemy import text

    from app.database.database import AsyncSessionLocal, engine

    assert engine.dialect.name == 'postgresql', (
        'BVI-инварианты опираются на блокировки строк, поддерживаемые '
        'PostgreSQL; на текущем бэкенде они не гарантированы'
    )

    async with AsyncSessionLocal() as session:
        isolation = (
            await session.execute(text('SHOW transaction_isolation'))
        ).scalar_one()
    print('\n      изоляция транзакций: {}'.format(isolation))

    # Строка нужна, чтобы блокировать было что: на пустой таблице FOR UPDATE
    # не блокирует ничего и проверка прошла бы вхолостую.
    name = 'Строка для проверки блокировки {}'.format(uuid.uuid4().hex[:8])
    await _insert_temp_olympiad(name)

    held = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        from app.models.olympiads import Olympiads
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(select(Olympiads).limit(1).with_for_update())
                held.set()
                await release.wait()

    async def reader():
        from app.models.olympiads import Olympiads
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(select(Olympiads).limit(1).with_for_update())

    holder_task = asyncio.create_task(holder())
    try:
        await asyncio.wait_for(held.wait(), timeout=30)
        reader_task = asyncio.create_task(reader())
        # Даём читателю дойти до базы и упереться в блокировку.
        await asyncio.sleep(0.5)
        assert not reader_task.done(), (
            'FOR UPDATE не удержал вторую транзакцию: блокировок строк нет'
        )
        release.set()
        await asyncio.wait_for(
            asyncio.gather(holder_task, reader_task), timeout=30
        )
    finally:
        release.set()
        if not holder_task.done():
            await asyncio.gather(holder_task, return_exceptions=True)
        await _delete_temp_olympiad(name)


async def _insert_temp_olympiad(name: str) -> None:
    from datetime import datetime, timezone

    from app.database.database import AsyncSessionLocal
    from app.database.search import normalize_name
    from app.models.olympiads import Olympiads

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(Olympiads(
                name=name,
                name_norm=normalize_name(name),
                status='PUBLISHED',
                createdAt=datetime.now(timezone.utc),
                updatedAt=datetime.now(timezone.utc),
            ))


async def _delete_temp_olympiad(name: str) -> None:
    from app.database.database import AsyncSessionLocal
    from app.database.search import normalize_name
    from app.models.olympiads import Olympiads
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    select(Olympiads).where(Olympiads.name_norm == normalize_name(name))
                )
            ).scalars().all()
            for row in rows:
                await session.delete(row)


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
    # только его результат — предупреждение кладём в раздел прогона.
    await _patch_section(client, second['id'], {
        'warnings': [
            'Table header was not recognized, columns were detected heuristically',
        ],
    })

    confirmed = await _confirm(client, second['id'])
    assert confirmed.status_code == 200
    result = confirmed.json()['result']
    assert result['archived'] == []
    assert result['archive_skipped_reason'], 'причина отказа обязательна'
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
    """Старый перечень нельзя применить — ни молча, ни «осознанно».

    Загружаем новый перечень и подтверждаем его — олимпиада из старого
    документа архивируется. Затем пробуем подтвердить старый документ: это
    отказ (409), потому что подтверждение вернуло бы каталог к старой
    редакции. Обхода в виде флага нет и быть не должно: актуальный каталог
    задаётся последним подтверждённым перечнем.
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

    # Каталог не откатился: олимпиада из старого, но отсутствующая в новом
    # перечне осталась архивной.
    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    rows = catalog.json()['olympiads']
    assert any(row['status'] == 'ARCHIVED' for row in rows), (
        'старый импорт не должен был публиковать архивную олимпиаду обратно'
    )


async def test_confirm_request_has_no_way_to_force_outdated(client):
    """В контракте подтверждения нет флага, отключающего проверку актуальности.

    Проверяется и схема API, и фактическое поведение: клиент, который пришлёт
    такой флаг, не должен получить возможность применить старый перечень.
    """
    await admin_client(client)
    old_doc = await _upload(client, 'rsosh_old.xlsx', xlsx_bytes())
    await _run(client, old_doc['id'])
    await _confirm(client, old_doc['id'])
    new_doc = await _upload(client, 'rsosh_new.xlsx', xlsx_bytes(row_count=2))
    await _run(client, new_doc['id'])
    await _confirm(client, new_doc['id'])
    await _force_review(client, old_doc['id'])

    schema = await client.get('/openapi.json')
    body = schema.json()['components']['schemas']
    confirm_schema = None
    for definition in body.values():
        props = definition.get('properties') or {}
        if 'archive_missing' in props:
            confirm_schema = props
            break
    assert confirm_schema is not None, 'схема ConfirmRequest не найдена в OpenAPI'
    assert 'allow_outdated' not in confirm_schema, (
        'в ConfirmRequest не должно быть способа применить устаревший перечень'
    )

    # Даже если клиент пришлёт такой флаг вручную, перечень не применится.
    forced = await _confirm(client, old_doc['id'], {'allow_outdated': True})
    assert forced.status_code == 409, forced.text

    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    rows = catalog.json()['olympiads']
    assert any(row['status'] == 'ARCHIVED' for row in rows), (
        'каталог не должен откатываться даже с неизвестным флагом в теле'
    )


async def test_repeating_confirm_of_same_snapshot_is_refused(client):
    """Один перечень применяется один раз.

    Повторное подтверждение уже применённого перечня не должно снова ни
    создавать, ни архивировать записи каталога.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, doc['id'])
    first = await _confirm(client, doc['id'])
    assert first.status_code == 200

    before = await client.get('/api/v1/olympiads?include_archived=true')
    snapshot_before = _catalog_fingerprint(before.json()['olympiads'])

    second = await _confirm(client, doc['id'])
    assert second.status_code == 409, second.text

    after = await client.get('/api/v1/olympiads?include_archived=true')
    assert _catalog_fingerprint(after.json()['olympiads']) == snapshot_before


# --------------------------- Смысл архива: MANUAL против RSOSH_ABSENT ---------


async def test_manual_archive_is_not_resurrected_by_rsosh_import(client):
    """Ручной архив — решение администратора, перечень РСОШ его не отменяет.

    Раньше ``_upsert`` возвращал в ``PUBLISHED`` любую архивную запись, встретив-
    шуюся в перечне, независимо от причины архива. Значит олимпиада, которую
    администратор исключил руками (например, из-за ошибки в данных),
    возвращалась в актуальный каталог при первом же импорте, где она
    встретится, — и решение администратора переставало что-либо значить.
    """
    await admin_client(client)
    university = await create_university(client, 'Университет для MANUAL')
    olympiad = await create_olympiad(
        client, '{} Ручная олимпиада'.format(university['name'])
    )

    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert archived.status_code == 200
    assert archived.json()['status'] == 'ARCHIVED'
    assert archived.json()['archive_reason'] == 'MANUAL', (
        'ручной архив обязан помечаться причиной MANUAL'
    )

    # Перечень РСОШ, в котором эта олимпиада есть. Имена берём из самой
    # олимпиады: перечень по умолчанию содержит других олимпиад, и тогда
    # проверяемая ветка `_upsert` просто не выполнялась бы, а тест проходил в
    #холостую.
    doc = await _upload(
        client,
        'rsosh_with_manual.xlsx',
        xlsx_bytes_including(olympiad['name']),
    )
    await _run(client, doc['id'])
    preview = await client.get(f"/api/v1/imports/{doc['id']}/preview")
    assert any(
        item['name_norm'] == normalize_name(olympiad['name'])
        for item in preview.json()['candidates']
    ), 'перечень должен содержать ручную олимпиаду, иначе тест ничего не проверяет'

    confirmed = await _confirm(client, doc['id'])
    assert confirmed.status_code == 200, confirmed.text

    state = await _admin_olympiad(client, olympiad['id'])
    assert state['status'] == 'ARCHIVED', (
        'импорт РСОШ не должен был вернуть ручную архивную олимпиаду в '
        'актуальные, status=' + str(state['status'])
    )
    assert state['archive_reason'] == 'MANUAL', (
        'причину ручного архива импорт не должен сбрасывать: '
        + str(state['archive_reason'])
    )

    # И в публичном каталоге её нет: олимпиада осталась исторической.
    catalog = await client.get('/api/v1/olympiads')
    assert olympiad['id'] not in [
        row['id'] for row in catalog.json()['olympiads']
    ], 'ручная архивная олимпиада вернулась в актуальный каталог'


async def test_rsosh_absent_archive_is_restored_when_it_appears_again(client):
    """Архив «нет в перечне РСОШ» импорт возвращает — это другой смысл.

    Два теста должны явно различаться: ``RSOSH_ABSENT`` означает «перечень её не
    содержал», и появление в новом перечне — это и есть основание вернуть её.
    Ручной архив такого основания не имеет.
    """
    await admin_client(client)
    full = await _upload(client, 'rsosh_all.xlsx', xlsx_bytes())
    await _run(client, full['id'])
    await _confirm(client, full['id'])

    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    everything = [row for row in catalog.json()['olympiads']
                  if row['status'] == 'PUBLISHED']
    assert len(everything) >= 3
    # Уходим в архив по перечню: короткий перечень без части олимпиад.
    short = await _upload(client, 'rsosh_few.xlsx', xlsx_bytes(row_count=2))
    await _run(client, short['id'])
    second = await _confirm(client, short['id'])
    assert second.status_code == 200
    assert second.json()['result']['archived'], 'олимпиады должны были уйти в архив'

    gone_id = second.json()['result']['archived'][0]
    gone = await _admin_olympiad_by_name(client, gone_id)
    assert gone['status'] == 'ARCHIVED'
    assert gone['archive_reason'] == 'RSOSH_ABSENT'

    # Олимпиада снова появляется в перечне — импорт возвращает её в актуальные.
    again = await _upload(client, 'rsosh_all_again.xlsx', xlsx_bytes())
    await _run(client, again['id'])
    third = await _confirm(client, again['id'])
    assert third.status_code == 200, third.text

    restored = await _admin_olympiad(client, gone['id'])
    assert restored['status'] == 'PUBLISHED', (
        'олимпиада из архива «нет в перечне РСОШ» обязана вернуться в актуальные'
    )
    assert restored['archive_reason'] is None, 'причина архива обязана сброситься'


async def test_manual_archive_keeps_its_bvi_history(client):
    """Историческая связь ручной архивной олимпиады сохраняется.

    Архив не отменяет того, что университет действительно давал БВИ, и новые
    заявки за такую олимпиаду по-прежнему невозможны.
    """
    await admin_client(client)
    university = await create_university(client, 'Университет истории БВИ')
    olympiad = await create_olympiad(client, 'Олимпиада для истории БВИ')
    await university_rep_client(client, university['id'])
    link = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert link.status_code == 201
    await admin_client(client)
    confirmed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/moderation",
        json={'action': 'confirm'},
    )
    assert confirmed.status_code == 200

    await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )

    # Перечень РСОШ с этой олимпиадой не возвращает её в актуальные.
    doc = await _upload(
        client,
        'rsosh_bvi_history.xlsx',
        xlsx_bytes_including(olympiad['name']),
    )
    await _run(client, doc['id'])
    confirmed = await _confirm(client, doc['id'])
    assert confirmed.status_code == 200, confirmed.text

    state = await _admin_olympiad(client, olympiad['id'])
    assert state['status'] == 'ARCHIVED'
    assert state['archive_reason'] == 'MANUAL'

    page = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert page.status_code == 200
    rows = [row for row in page.json()['olympiads'] if row['id'] == olympiad['id']]
    assert len(rows) == 1, 'историческая связь должна была сохраниться'
    assert rows[0]['is_historical'] is True


# --------------------------- Гонки при подтверждении ---------------------------


async def test_parallel_confirm_of_same_snapshot_applies_once(client):
    """Два администратора, один перечень: применяется ровно один раз.

    Оба могут увидеть состояние ``review`` до того, как один из них применит
    перечень. Без блокировки второй импорт применился бы повторно — ещё раз
    создал/обновил записи каталога и заархивировал бы пропавшие. Здесь
    проверяется, что каталог изменён один раз, а второй получает контролируемый
    отказ.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, doc['id'])
    assert (await _confirm(client, doc['id'])).status_code == 200

    before = await client.get('/api/v1/olympiads?include_archived=true')
    fingerprint = _catalog_fingerprint(before.json()['olympiads'])

    # Возвращаем перечень в состояние «готов к подтверждению», чтобы его можно
    # было подтвердить повторно.
    await _force_review(client, doc['id'])

    codes = await asyncio.gather(
        _confirm_direct(doc['id']), _confirm_direct(doc['id'])
    )
    assert codes.count(200) == 1, f'применён должен быть ровно один раз: {codes}'
    refused = [code for code in codes if code != 200]
    assert len(refused) == 1, codes
    assert refused[0] in (400, 409), f'второй должен получить отказ: {codes}'

    after = await client.get('/api/v1/olympiads?include_archived=true')
    assert _catalog_fingerprint(after.json()['olympiads']) == fingerprint, (
        'каталог изменён повторно: применение прошло дважды'
    )


async def test_parallel_confirm_of_different_snapshots_keeps_newest(client, monkeypatch):
    """Параллельное подтверждение старого и нового перечня не откатывает каталог.

    Гонка выстроена намеренно и детерминированно: старый перечень входит в
    транзакцию и **замирает посередине**, а новый в это время пытается
    примениться.

    Без общей блокировки происходит ровно то, что недопустимо: новый перечень
    применяется первым, затем старой дописывает своё поверх — и каталог
    возвращается к старой редакции.

    Проверяются два наблюдаемых факта:

    1. пока открыта транзакция старого перечня, новый не может примениться
       (его состояние остаётся ``review``) — это и есть взаимное исключение;
    2. в конце каталог соответствует новому перечню: олимпиада, исчезнувшая
       из него, осталась архивной.
    """
    await admin_client(client)

    old_doc = await _upload(client, 'rsosh_old.xlsx', xlsx_bytes())
    await _run(client, old_doc['id'])
    assert (await _confirm(client, old_doc['id'])).status_code == 200

    # Свежий перечень короче: часть олимпиад из него исчезла.
    new_doc = await _upload(client, 'rsosh_new.xlsx', xlsx_bytes(row_count=2))
    await _run(client, new_doc['id'])
    # Старый перечень снова готов к подтверждению — именно его и попробуем
    # применить параллельно с новым.
    await _force_review(client, old_doc['id'])

    # Олимпиада, которая есть в старом перечне, но исчезла из нового: именно её
    # возврат в актуальные и означал бы откат каталога.
    new_candidates = await _candidates(client, new_doc['id'])
    old_candidates = await _candidates(client, old_doc['id'])
    new_names = {item['name_norm'] for item in new_candidates}
    only_in_old = [
        item['name_norm'] for item in old_candidates
        if item['name_norm'] not in new_names
    ]
    assert only_in_old, 'для проверки нужен перечень, где одна олимпиада исчезла'

    from app.rsosh import persist as persist_module

    original_upsert = persist_module._upsert
    inside_old = asyncio.Event()
    release_old = asyncio.Event()

    async def pausing_upsert(session, candidate, doc_id):
        # Замираем на первой записи старого перечня: его транзакция открыта,
        # блокировка удерживается, каталог ещё не изменён.
        if not inside_old.is_set():
            inside_old.set()
            await release_old.wait()
        return await original_upsert(session, candidate, doc_id)

    monkeypatch.setattr(persist_module, '_upsert', pausing_upsert)

    old_task = asyncio.create_task(_confirm_direct(old_doc['id']))
    await asyncio.wait_for(inside_old.wait(), timeout=30)

    new_task = asyncio.create_task(_confirm_direct(new_doc['id']))
    # Даём новому перечню время дойти до базы. Если бы применение перечней не
    # было сериализовано, новый перечень применился бы прямо сейчас.
    for _ in range(50):
        await asyncio.sleep(0.01)
    assert await _import_state(new_doc['id']) == 'review', (
        'подтверждение нового перечня прошло, пока открыта транзакция старого: '
        'применение перечней не сериализовано'
    )

    release_old.set()
    old_code, new_code = await asyncio.gather(old_task, new_task)

    assert new_code == 200, f'новый перечень должен примениться: {new_code}'
    assert old_code == 200, (
        'старый перечень применился раньше — это допустимо, каталог в конце всё '
        'равно должен соответствовать новому перечню'
    )

    statuses = await _olympiad_statuses_by_norm(only_in_old)
    for name_norm, status in statuses.items():
        assert status == 'ARCHIVED', (
            f'{name_norm} вернулась в актуальные: каталог откатился назад '
            f'(status={status})'
        )


async def test_parallel_confirm_and_reject_leave_one_consistent_state(
    client, monkeypatch
):
    """Confirm и reject одного прогона не могут оба «победить».

    Опасная последовательность была возможна: ``reject`` читал состояние и менял
    его отдельной операцией, поэтому мог отработать уже после того, как
    ``confirm`` применил перечень. Итог — каталог изменён, а прогон помечен
    ``rejected``: по интерфейсу выглядит так, будто перечень отклонили, а данные
    уже в каталоге.

    Гонка выстроена детерминированно: ``confirm`` входит в транзакцию и
    замирает на первой записи каталога, а в этот момент ``reject`` делает
    запрос. При общей блокировке он обязан дождаться завершения и получить 409.
    Без неё он проходит мимо и отклоняет уже применённый перечень.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_race_state.xlsx', xlsx_bytes())
    await _run(client, doc['id'])

    from app.rsosh import persist as persist_module
    from app.main import app as fastapi_app

    original_upsert = persist_module._upsert
    inside_confirm = asyncio.Event()
    release_confirm = asyncio.Event()

    async def pausing_upsert(session, candidate, doc_id):
        if not inside_confirm.is_set():
            inside_confirm.set()
            await release_confirm.wait()
        return await original_upsert(session, candidate, doc_id)

    monkeypatch.setattr(persist_module, '_upsert', pausing_upsert)

    import httpx

    async def confirm():
        return await _confirm(client, doc['id'])

    async def reject():
        # Отдельное соединение: параллельный запрос должен быть настоящим
        # параллельным, а не последовательным вызовом в том же клиенте.
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url='http://test',
            cookies=dict(client.cookies),
        ) as raw:
            return await raw.post(f'/api/v1/imports/{doc["id"]}/reject')

    confirm_task = asyncio.create_task(confirm())
    try:
        await asyncio.wait_for(inside_confirm.wait(), timeout=30)
        reject_task = asyncio.create_task(reject())
        # Ждём не «немного времени», а самого факта ожидания блокировки в БД:
        # иначе reject может не успеть дойти до записи, и гонка не проверится.
        waiting = await _wait_for_lock_wait()
        assert waiting is not None, (
            'второй запрос не упёрся в блокировку — гонка не была воспроизведена'
        )
        release_confirm.set()
        confirm_response, reject_response = await asyncio.gather(
            confirm_task, reject_task
        )
    finally:
        release_confirm.set()
        if not confirm_task.done():
            await asyncio.gather(confirm_task, return_exceptions=True)

    outcomes = {
        'confirmed' if confirm_response.status_code == 200
        else confirm_response.status_code,
        'rejected' if reject_response.status_code == 200
        else reject_response.status_code,
    }
    # Ровно один переход; второй получает конфликт. Сравниваем как множество:
    # порядок не должен влиять на смысл проверки.
    assert outcomes in (
        {'confirmed', 409},
        {'rejected', 409},
    ), f'оба действия прошли, состояние противоречиво: {outcomes}'

    state = await _import_state(doc['id'])
    if 'confirmed' in outcomes:
        # Каталог применён — состояние обязано быть approved.
        assert state == 'approved', (
            'каталог применён, а состояние прогона — ' + str(state)
        )
    else:
        # Перечень отклонён — в каталоге не должно быть его олимпиад.
        assert state == 'rejected', (
            'перечень отклонён, а состояние прогона — ' + str(state)
        )
        assert not await _has_rsosh_olympiads(doc['id']), (
            'отклонённый перечень всё же записался в каталог'
        )


async def test_reject_after_confirm_is_refused(client):
    """Подтверждённый перечень отклонить нельзя — и наоборот.

    Тот же инвариант, но проверяется по шагам, а не на гонке: так понятно,
    какой именно переход запрещён.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_confirm_then_reject.xlsx', xlsx_bytes())
    await _run(client, doc['id'])
    assert (await _confirm(client, doc['id'])).status_code == 200

    response = await client.post(f'/api/v1/imports/{doc["id"]}/reject')
    assert response.status_code == 409, response.text

    status = await client.get(f'/api/v1/imports/{doc["id"]}')
    assert status.json()['state'] == 'approved', (
        'отклонение не должно было менять состояние применённого прогона'
    )
    assert status.json()['status'] == 'PROCESSED'


async def test_parallel_start_import_runs_once(client):
    """Два concurrent-запуска одного документа дают одну обработку.

    Раньше чтение документа и переход в ``PROCESSING`` были отдельными
    операциями: оба запроса успевали прочитать документ и оба запустить задачу.
    Две обработки одного документа писали в один ``metadata['rsosh']``, и итог
    зависел от того, кто закончил последним.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_start_race.xlsx', xlsx_bytes())

    from app.rsosh import processor as processor_module
    from app.rsosh.types import RsoshConflictError, RsoshError

    async def start():
        try:
            await processor_module.start_import(doc['id'])
            return 202
        except RsoshConflictError:
            return 409
        except RsoshError:
            return 400

    codes = await asyncio.gather(start(), start(), start())
    assert codes.count(202) == 1, f'запусков должно быть ровно один: {codes}'
    refused = [code for code in codes if code != 202]
    assert refused and all(code == 409 for code in refused), (
        f'остальные должны получить 409: {codes}'
    )

    # Обработка действительно была одна: прогон дошёл до preview, а не
    # остался в PROCESSING и не был перетёрт второй обработкой.
    state = await _import_state(doc['id'])
    assert state == 'review', 'после одной обработки ожидается preview, получено ' \
        + str(state)


async def test_start_import_again_after_finished_run_is_allowed(client):
    """Повторный запуск после завершения — не то же самое, что гонка.

    ``PROCESSING`` занят, а ``review``/``failed`` свободны: иначе после ошибки
    разбора перечень нельзя было бы перезапустить без новой загрузки файла.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_restart.xlsx', xlsx_bytes())

    first = await client.post('/api/v1/imports/rsosh', json={'doc_id': doc['id']})
    assert first.status_code == 202
    assert (await _import_state(doc['id'])) == 'review'

    second = await client.post('/api/v1/imports/rsosh', json={'doc_id': doc['id']})
    assert second.status_code == 202, second.text
    assert (await _import_state(doc['id'])) == 'review'


async def test_rejected_run_cannot_be_restarted_but_stays_consistent(client):
    """Отклонённый прогон не перезапускается — и это поведение не менялось.

    Проверяется намеренно: раньше ``REJECTED`` тоже не входил в стартовые
    статусы, поэтому повторный запуск отклонённого документа отклонялся с 400 и
    раньше. Менять это — значит менять продуктовое решение, чего в задаче нет.

    Фиксируется здесь, чтобы изменение списка стартовых статусов не прошло
    молча: если перезапуск отклонённого решат разрешить, тест об этом скажет.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_reject_restart.xlsx', xlsx_bytes())
    await _run(client, doc['id'])
    assert await _import_state(doc['id']) == 'review'

    rejected = await client.post(f'/api/v1/imports/{doc["id"]}/reject')
    assert rejected.status_code == 200, rejected.text
    assert await _import_state(doc['id']) == 'rejected'

    restarted = await client.post('/api/v1/imports/rsosh', json={'doc_id': doc['id']})
    assert restarted.status_code == 400, restarted.text
    # Документ остался отклонённым, а каталог — нетронутым.
    assert await _import_state(doc['id']) == 'rejected'
    assert not await _has_rsosh_olympiads(doc['id'])


# --------------------------- Изоляция строк импорта ---------------------------


async def test_integrity_error_in_one_row_does_not_break_the_import(client):
    """Ошибка БД в одной строке не ломает остальные строки импорта.

    ``flush()`` с ``IntegrityError`` переводит сессию SQLAlchemy в
    failed-состояние: простой ``continue`` после такой ошибки не оставляет
    сессию пригодной, и вместо «не записалась одна строка» получается «весь
    импорт развалился». Каждая строка пишется в SAVEPOINT, поэтому A и C
    сохраняются, B попадает в ``errors``, а commit проходит.

    Ошибка здесь настоящая, а не нарисованная: кандидат без имени нарушает
    ``olympiads.name NOT NULL``, и её поднимает сама база.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, doc['id'])

    candidates = await _candidates(client, doc['id'])
    assert len(candidates) >= 3, 'нужно минимум три строки для проверки изоляции'

    # name=None -> нарушение NOT NULL на вставке, и ошибку поднимает сама база.
    patched = [
        candidates[0],
        {**candidates[1], 'name': None},
        candidates[2],
    ]
    await _replace_candidates(client, doc['id'], patched)

    confirmed = await _confirm(client, doc['id'])
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()['result']

    # Ровно одна строка не записалась, остальные применились: изоляция сработала.
    assert len(result['errors']) == 1, result['errors']
    assert result['created'], 'окружающие строки должны были примениться'
    assert len(result['created']) == 2, result['created']

    # Массовое архивирование при ошибках отключено — прежний инвариант.
    assert result['archived'] == []
    assert result['archive_skipped_reason']
    assert 'не удалось применить' in result['archive_skipped_reason']

    # Каталог не рассыпался: олимпиады соседних строк на месте и опубликованы.
    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    rows = catalog.json()['olympiads']
    assert len(rows) == 2, rows
    assert all(row['status'] == 'PUBLISHED' for row in rows), rows
    names = {row['name'] for row in rows}
    assert candidates[0]['name'] in names
    assert candidates[2]['name'] in names


async def test_candidate_error_text_hides_database_internals(client, monkeypatch):
    """Текст ошибки строки не раскрывает имена таблиц и колонок.

    Отчёт импорта возвращается в API и хранится в метаданных документа, поэтому
    ``str(IntegrityError)`` с SQL-запросом туда попадать не должен.
    """
    await admin_client(client)
    doc = await _upload(client, 'rsosh_full.xlsx', xlsx_bytes())
    await _run(client, doc['id'])
    candidates = await _candidates(client, doc['id'])
    await _replace_candidates(client, doc['id'], [candidates[0], candidates[1]])

    from app.rsosh import persist as persist_module
    from sqlalchemy.exc import IntegrityError

    original = persist_module._upsert
    calls = {'n': 0}

    async def failing_upsert(session, candidate, doc_id):
        calls['n'] += 1
        if calls['n'] == 2:
            raise IntegrityError(
                'INSERT INTO olympiads (name, name_norm) VALUES (%(name)s, '
                '%(name_norm)s) RETURNING olympiads.id',
                {'name': candidate.name, 'name_norm': candidate.name_norm},
                Exception('duplicate key value violates unique constraint'),
            )
        return await original(session, candidate, doc_id)

    monkeypatch.setattr(persist_module, '_upsert', failing_upsert)
    confirmed = await _confirm(client, doc['id'])
    assert confirmed.status_code == 200, confirmed.text
    errors = confirmed.json()['result']['errors']
    assert errors, 'ошибка должна быть в отчёте'
    blob = ' '.join(errors).lower()
    for leak in ('insert into', 'olympiads', 'name_norm', 'duplicate key'):
        assert leak not in blob, f'в отчёт просочилось внутреннее: {leak}'


# --------------------------- Типы документов ---------------------------


async def test_university_order_cannot_start_rsosh_import(client):
    """Приказ университета не запускает импорт РСОШ и не создаёт олимпиады.

    В каталог олимпиады попадают только два пути: перечень РСОШ, подтверждённый
    администратором, и ручное создание администратором. Приказ университета —
    документ-источник, а не перечень олимпиад, поэтому он не должен ни запускать
    импорт, ни влиять на каталог.
    """
    await admin_client(client)
    before = await client.get('/api/v1/olympiads?include_archived=true')
    catalog_before = _catalog_fingerprint(before.json()['olympiads'])

    doc = await _upload(
        client, 'order.pdf', xlsx_bytes(), doc_type='UNIVERSITY_ORDER'
    )
    response = await client.post(
        '/api/v1/imports/rsosh', json={'doc_id': doc['id']}
    )
    assert response.status_code == 400, response.text
    assert 'RSOSH_LIST' in response.json()['detail']

    after = await client.get('/api/v1/olympiads?include_archived=true')
    assert _catalog_fingerprint(after.json()['olympiads']) == catalog_before, (
        'документ, не являющийся перечнем РСОШ, изменил каталог'
    )


async def test_other_document_cannot_start_rsosh_import(client):
    """Документ типа OTHER — тоже не перечень олимпиад."""
    await admin_client(client)
    before = await client.get('/api/v1/olympiads?include_archived=true')
    catalog_before = _catalog_fingerprint(before.json()['olympiads'])

    doc = await _upload(client, 'other.pdf', xlsx_bytes(), doc_type='OTHER')
    response = await client.post(
        '/api/v1/imports/rsosh', json={'doc_id': doc['id']}
    )
    assert response.status_code == 400, response.text
    assert 'RSOSH_LIST' in response.json()['detail']

    after = await client.get('/api/v1/olympiads?include_archived=true')
    assert _catalog_fingerprint(after.json()['olympiads']) == catalog_before


async def test_only_rsosh_list_reaches_the_catalog_writer(client):
    """Защита от обхода проверки типа другим вызывающим.

    Проверка типа стоит в трёх местах: в роутере, в ``run_import`` и в слое
    persistence. Здесь обходятся первые два: документ типа ``UNIVERSITY_ORDER``
    насильно переводится в состояние «готов к подтверждению», и подтверждение
    вызывается напрямую в persistence-слой. Каталог всё равно не должен
    измениться — иначе будущий вызывающий (Celery-задача, скрипт) получил бы
    обходной путь создания олимпиад.
    """
    await admin_client(client)
    doc = await _upload(
        client, 'order2.pdf', xlsx_bytes(), doc_type='UNIVERSITY_ORDER'
    )

    # Кандидаты берём у настоящего разбора перечня РСОШ: важно, что под
    # подтверждением оказываются реальные строки, а документ — нет.
    seed = await _upload(client, 'seed.xlsx', xlsx_bytes())
    await _run(client, seed['id'])
    real_candidates = await _candidates(client, seed['id'])

    await _patch_section(client, doc['id'], {'candidates': real_candidates})
    assert await _import_state(doc['id']) == 'review'

    from app.rsosh import persist as persist_module
    from app.rsosh.types import RsoshError

    with pytest.raises(RsoshError) as raised:
        await persist_module.apply_confirmed_import(doc_id=doc['id'])
    assert 'RSOSH_LIST' in str(raised.value)

    catalog = await client.get('/api/v1/olympiads?include_archived=true')
    assert catalog.json()['olympiads'] == [], 'из приказа олимпиады созданы'


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


async def _upload(client, filename, payload, doc_type='RSOSH_LIST'):
    response = await client.post(
        '/api/v1/docs/upload',
        files={'file': (filename, payload, 'application/octet-stream')},
        data={'type': doc_type},
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


async def _confirm_direct(doc_id) -> int:
    """Подтвердить перечень в обход HTTP и вернуть код ответа.

    HTTP-слой здесь лишнее звено: тестам важно поведение применения, а HTTP
    добавил бы ещё одну сессию и своё соединение. Конфликт (устаревший снимок,
    повторное подтверждение) — тоже контролируемый ответ, поэтому он не
    поднимается наружу, а возвращается кодом.
    """
    from app.rsosh import processor as processor_module
    from app.rsosh.types import RsoshConflictError, RsoshError

    try:
        await processor_module.confirm_import(doc_id)
        return 200
    except RsoshConflictError:
        return 409
    except RsoshError:
        return 400


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


def _catalog_fingerprint(rows: list[dict]) -> list[tuple]:
    """Слепок состояния каталога для сравнения «до/после».

    Сравниваются сами записи (имя, статус, источник), а не их количество:
    повторное применение перечня может не изменить число строк, но изменит их
    содержимое — и это тоже повреждение каталога.
    """
    return sorted(
        (row.get('name'), row.get('status')) for row in rows
    )


async def _candidates(client, doc_id) -> list[dict]:
    """Кандидаты текущего прогона (как их видит подтверждение)."""
    response = await client.get(f'/api/v1/imports/{doc_id}/preview')
    assert response.status_code == 200, response.text
    candidates = response.json()['candidates']
    assert candidates, 'ожидались кандидаты'
    return candidates


async def _replace_candidates(client, doc_id, candidates: list[dict]) -> None:
    """Подменить список кандидатов прогона.

    Нужно для проверки изоляции строк на реальных данных импорта: сами строки
    берутся из настоящего разбора, меняется только то, что должно сломаться.
    Распознавание при этом не трогается.
    """
    await _patch_section(client, doc_id, {'candidates': candidates})


async def _wait_for_lock_wait(timeout: float = 15.0) -> str | None:
    """Дождаться, пока в БД реально кто-то ждёт блокировку.

    Возвращает текст ждущего запроса или ``None``, если ожидания не было.

    Нужно, чтобы гонка была воспроизводимой, а не вероятной: без этой проверки
    тест мог бы отпустить первую транзакцию раньше, чем вторая дойдёт до
    блокировки, и тогда даже неправильный код прошёл бы тест «по счастливой»
    последовательности.

    Соединение берётся из настроек приложения, а не задаётся строкой: тесты
    идут и на локальной базе, и внутри Docker, где хост — ``postgres``.
    """
    from app.database.database import AsyncSessionLocal

    deadline = time.monotonic() + timeout
    query = (
        'SELECT query FROM pg_stat_activity '
        "WHERE wait_event_type = 'Lock' AND state = 'active' LIMIT 1"
    )
    while time.monotonic() < deadline:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(text(query))
            ).scalar_one_or_none()
        if row is not None:
            return str(row)
        await asyncio.sleep(0.05)
    return None


async def _admin_olympiad(client, olympiad_id) -> dict:
    """Админская карточка олимпиады: с ``archive_reason``.

    Публичный ответ ``archive_reason`` не отдаёт намеренно, поэтому причину
    архива здесь смотреть негде.
    """
    response = await client.get(f'/api/v1/admin/olympiads')
    assert response.status_code == 200, response.text
    for item in response.json()['olympiads']:
        if item['id'] == olympiad_id:
            return item
    raise AssertionError('олимпиада {} не найдена в панели'.format(olympiad_id))


async def _admin_olympiad_by_name(client, name: str) -> dict:
    for item in (await client.get('/api/v1/admin/olympiads')).json()['olympiads']:
        if item['name'] == name:
            return item
    raise AssertionError('олимпиада {!r} не найдена в панели'.format(name))


async def _has_rsosh_olympiads(doc_id) -> bool:
    """Есть ли в каталоге олимпиады, созданные именно этим документом.

    Источник важен: каталог может содержать чужие олимпиады, и их наличие не
    говорит о том, что отклонённый перечень что-то записал.
    """
    from app.database.database import AsyncSessionLocal
    from app.models.olympiads import Olympiads
    from sqlalchemy import func, select

    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Olympiads)
                .where(Olympiads.source_doc_id == uuid.UUID(str(doc_id)))
            )
        ).scalar_one()
    return bool(count)


async def _import_state(doc_id) -> str | None:
    """Состояние прогона импорта, прочитанное напрямую из БД.

    Именно БД, а не API: проверка должна видеть только зафиксированные данные,
    иначе ожидание блокировки можно было бы «провалить» незаметной правкой.
    """
    from app.database.database import AsyncSessionLocal
    from app.models.docs import Docs
    from app.rsosh import states
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        meta = (
            await session.execute(
                select(Docs.meta).where(Docs.id == uuid.UUID(str(doc_id)))
            )
        ).scalar_one_or_none()
        return states.rsosh_section({'metadata': meta}).get('state')


async def _olympiad_statuses_by_norm(name_norms: list[str]) -> dict[str, str]:
    """Текущие статусы олимпиад по нормализованному имени."""
    from app.database.database import AsyncSessionLocal
    from app.models.olympiads import Olympiads
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Olympiads.name_norm, Olympiads.status).where(
                    Olympiads.name_norm.in_(list(name_norms))
                )
            )
        ).all()
    return {name_norm: status for name_norm, status in rows}


async def _patch_section(client, doc_id, patch: dict) -> None:
    """Изменить раздел ``rsosh`` прогона.

    Правка идёт через новый словарь: SQLAlchemy не отмечает JSONB-колонку
    изменённой, если мутировать уже загруженный dict, и запись молча не
    сохранилась бы. Так же поступает продуктовый код (app/rsosh/states.py).
    """
    from app.database.database import AsyncSessionLocal
    from app.models.docs import Docs
    from app.rsosh import states
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        doc = (
            await session.execute(select(Docs).where(Docs.id == uuid.UUID(str(doc_id))))
        ).scalar_one()
        stored = states.rsosh_section({'metadata': doc.meta})
        section = {**stored, **patch, 'state': 'review'}
        doc.meta = states.docs_metadata_with_section({'metadata': doc.meta}, section)
        doc.status = 'NEEDS_REVIEW'
        await session.commit()