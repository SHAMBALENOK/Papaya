"""Контракт канонической модели MVP.

Проверяется основной сценарий «олимпиада → сезон → профиль → правило льготы →
документ» и то, что вокруг него не осталось legacy-понятий: отдельной заявки
БВИ, источников, дат сезона, свободного текста результата и связи правил с
программами.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_benefit_rule,
    create_olympiad,
    create_profile,
    create_season,
    create_university,
    university_rep_client,
    upload_university_doc,
)


async def _context(client, name='Университет ИТМО'):
    await admin_client(client)
    university = await create_university(client, name)
    olympiad = await create_olympiad(client, f'Олимпиада {name}')
    season = await create_season(client, olympiad['id'])
    profile = await create_profile(client, season['id'])
    doc = await upload_university_doc(client, university['id'])
    return university, olympiad, season, profile, doc


async def _create_rule(client, ctx, **fields):
    university, olympiad, season, profile, doc = ctx
    return await client.post(
        f"/api/v1/universities/{university['id']}/benefits",
        json={
            'olympiad_id': olympiad['id'],
            'season_id': season['id'],
            'profile_id': profile['id'],
            'benefit_type': 'BVI',
            'required_result_type': 'WINNER',
            'doc_id': doc['id'],
            **fields,
        },
    )


# ------------------------------ Основной сценарий ------------------------------


async def test_canonical_flow_from_season_to_verified_rule(client):
    university, olympiad, season, profile, doc = await _context(client)
    await university_rep_client(client, university['id'])

    created = await _create_rule(client, (university, olympiad, season, profile, doc))
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule['verification_status'] == 'unverified'
    assert rule['season_id'] == season['id']
    assert rule['profile_id'] == profile['id']
    assert rule['doc']['id'] == doc['id']
    assert rule['required_result_type'] == 'WINNER'
    assert rule['ege_requirement'] is None

    # Публично непроверенное опубликованное правило видно с честным статусом.
    public = await client.get('/api/v1/benefits')
    assert public.status_code == 200
    row = next(item for item in public.json()['rules'] if item['id'] == rule['id'])
    assert row['verification_status'] == 'unverified'
    assert row['season_label'] == season['season_label']
    assert row['profile_name'] == profile['name']
    assert row['profile_rsosh_level'] == '1'

    # Представитель видит свой рабочий список, но подтвердить правило не может.
    managed = await client.get(
        f"/api/v1/universities/{university['id']}/benefit-rules/manage"
    )
    assert managed.status_code == 200
    assert [item['id'] for item in managed.json()['rules']] == [rule['id']]
    denied = await client.post(f"/api/v1/benefits/{rule['id']}/verify")
    assert denied.status_code == 403

    # Подтверждает администратор; документ уже приложен представителем.
    await admin_client(client)
    verified = await client.post(f"/api/v1/benefits/{rule['id']}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()['verification_status'] == 'verified'

    versions = await client.get(f"/api/v1/benefits/{rule['id']}/versions")
    assert versions.status_code == 200
    assert len(versions.json()['versions']) >= 1


async def test_season_has_no_dates_or_availability(client):
    """Сезон — олимпиада и метка. Дат и доступности в контракте нет."""
    await admin_client(client)
    olympiad = await create_olympiad(client, 'Олимпиада без дат')
    created = await client.post(
        f"/api/v1/olympiads/{olympiad['id']}/seasons",
        json={
            'season_label': '2026/2027',
            'registration_start': '2026-09-01T00:00:00Z',
            'event_start': '2026-10-01T00:00:00Z',
            'rsosh_level': '1',
            'availability': 'free',
        },
    )
    assert created.status_code in (200, 201), created.text
    body = created.json()
    for field in ('registration_start', 'registration_end', 'event_start',
                  'event_end', 'rsosh_level', 'availability'):
        assert field not in body, f'{field} больше не хранится в сезоне'
    assert set(body).issuperset({'id', 'olympiad_id', 'season_label'})


async def test_profile_level_is_required_to_be_valid(client):
    """Уровень РСОШ — только 1, 2, 3 или пусто."""
    await admin_client(client)
    olympiad = await create_olympiad(client, 'Олимпиада уровней')
    season = await create_season(client, olympiad['id'])

    good = await create_profile(client, season['id'], 'Математика', '2')
    assert good['rsosh_level'] == '2'

    bad = await client.post(
        f"/api/v1/seasons/{season['id']}/profiles",
        json={'name': 'Неверный уровень', 'rsosh_level': '4'},
    )
    assert bad.status_code == 422

    empty = await create_profile(client, season['id'], 'Без уровня', None)
    assert empty['rsosh_level'] is None


# ------------------------------ ЕГЭ и результат ------------------------------


async def test_ege_requirement_is_separate_optional_structure(client):
    """ЕГЭ — отдельная необязательная структура, а не поле профиля."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])

    created = await _create_rule(
        client, ctx,
        required_result_type='WINNER_OR_PRIZE',
        ege_requirement={'subject': 'Математика', 'min_score': 75},
    )
    assert created.status_code == 200, created.text
    ege = created.json()['ege_requirement']
    assert ege == {'subject': 'Математика', 'min_score': 75}

    invalid = await _create_rule(
        client, ctx,
        required_result_type='PRIZE',
        ege_requirement={'subject': 'Математика', 'min_score': 101},
    )
    assert invalid.status_code == 422


async def test_result_type_rejects_free_text(client):
    """Свободный текст результата больше не принимается."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])

    response = await _create_rule(
        client, ctx, required_result_type='победитель или призёр'
    )
    assert response.status_code == 422


async def test_ege_requirement_cleared_on_update(client):
    """Требование ЕГЭ можно снять: правило остаётся валидным."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])
    created = await _create_rule(
        client, ctx, ege_requirement={'subject': 'Физика', 'min_score': 60},
    )
    rule = created.json()

    updated = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={'version': rule['version'], 'ege_requirement': None},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()['ege_requirement'] is None


# ------------------------------ Версии ------------------------------


async def test_update_requires_current_version(client):
    """Устаревшая версия при правке — 409, данные не перезаписываются."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])
    created = await _create_rule(client, ctx)
    rule = created.json()

    ok = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={'version': rule['version'], 'required_result_type': 'PRIZE'},
    )
    assert ok.status_code == 200

    stale = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={'version': rule['version'], 'required_result_type': 'WINNER'},
    )
    assert stale.status_code == 409

    fresh = await client.get(f"/api/v1/benefits/{rule['id']}")
    assert fresh.json()['required_result_type'] == 'PRIZE'


async def test_rollback_restores_snapshot_and_unverifies(client):
    """Откат атомарен, создаёт новую версию и снимает проверку."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])
    created = await _create_rule(client, ctx)
    rule = created.json()

    changed = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={
            'version': rule['version'],
            'required_result_type': 'WINNER_OR_PRIZE',
            'ege_requirement': {'subject': 'Информатика', 'min_score': 80},
        },
    )
    assert changed.status_code == 200
    current = changed.json()

    conflict = await client.post(
        f"/api/v1/benefits/{rule['id']}/rollback",
        json={'version': 1, 'expected_version': 777},
    )
    assert conflict.status_code == 409

    rolled = await client.post(
        f"/api/v1/benefits/{rule['id']}/rollback",
        json={'version': 1, 'expected_version': current['version']},
    )
    assert rolled.status_code == 200, rolled.text
    body = rolled.json()
    assert body['version'] > current['version']
    assert body['required_result_type'] == 'WINNER'
    assert body['ege_requirement'] is None
    assert body['verification_status'] == 'unverified'


async def test_versions_are_isolated_between_universities(client):
    """Представитель чужого вуза не читает рабочие версии правила."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])
    created = await _create_rule(client, ctx)

    other = await create_university(client, 'Второй университет')
    await university_rep_client(client, other['id'])
    response = await client.get(
        f"/api/v1/benefits/{created.json()['id']}/versions/manage"
    )
    assert response.status_code == 403


# ------------------------------ Каталог ------------------------------


async def test_public_catalog_combines_filters_and_reports_total(client):
    """Фильтры комбинируются на сервере, `total` соответствует выборке."""
    first = await _context(client, 'Университет ИТМО')
    second = await _context(client, 'Университет МФТИ')

    await university_rep_client(client, first[0]['id'])
    one = await _create_rule(client, first, benefit_type='BVI')
    two = await _create_rule(
        client, first, benefit_type='EGE_100', required_result_type='PRIZE',
        ege_requirement={'subject': 'Математика', 'min_score': 70},
    )
    await university_rep_client(client, second[0]['id'])
    other = await _create_rule(client, second, benefit_type='BVI')

    only_bvi = await client.get(
        '/api/v1/benefits',
        params={'benefit_type': 'BVI'},
    )
    assert only_bvi.status_code == 200
    ids = {item['id'] for item in only_bvi.json()['rules']}
    assert ids == {one.json()['id'], other.json()['id']}
    assert only_bvi.json()['total'] == 2

    by_university = await client.get(
        '/api/v1/benefits',
        params={'university_id': first[0]['id'], 'benefit_type': 'EGE_100'},
    )
    assert by_university.json()['total'] == 1
    assert by_university.json()['rules'][0]['id'] == two.json()['id']

    by_level = await client.get('/api/v1/benefits', params={'level': '1'})
    assert by_level.json()['total'] == 3

    nothing = await client.get('/api/v1/benefits', params={'level': '3'})
    assert nothing.json()['total'] == 0
    assert nothing.json()['rules'] == []


async def test_public_catalog_pagination_keeps_filters(client):
    """Пагинация считает `total` по фильтру, а не по всему каталогу."""
    ctx = await _context(client)
    university, olympiad, season, _, doc = ctx
    # Правила должны отличаться профилем: одна опубликованная льгота на
    # «вуз + олимпиада + сезон + профиль + тип» защищена уникальным индексом.
    profiles = [
        await create_profile(client, season['id'], f'Профиль {index}')
        for index in range(3)
    ]
    await university_rep_client(client, university['id'])
    created = []
    for index, profile in enumerate(profiles):
        response = await _create_rule(
            client, (university, olympiad, season, profile, doc),
            benefit_type='EGE_100',
            required_result_type='PRIZE',
            ege_requirement={'subject': f'Предмет {index}', 'min_score': 60},
        )
        assert response.status_code == 200
        created.append(response.json())

    page = await client.get(
        '/api/v1/benefits',
        params={'benefit_type': 'EGE_100', 'limit': 1, 'offset': 1},
    )
    assert page.status_code == 200
    body = page.json()
    assert body['total'] == 3
    assert len(body['rules']) == 1
    assert body['rules'][0]['id'] in {item['id'] for item in created}


async def test_olympiad_season_rules_do_not_mix(client):
    """Правила разных сезонов не смешиваются на странице олимпиады."""
    ctx = await _context(client)
    await university_rep_client(client, ctx[0]['id'])
    first_rule = await _create_rule(client, ctx)

    await admin_client(client)
    next_season = await create_season(client, ctx[1]['id'], '2024/2025')
    next_profile = await create_profile(client, next_season['id'], 'Физика', '2')
    next_rule = await _create_rule(
        client, (ctx[0], ctx[1], next_season, next_profile, ctx[4])
    )
    assert next_rule.status_code == 200

    current = await client.get(
        f"/api/v1/benefits/olympiad/{ctx[1]['id']}",
        params={'season_id': ctx[2]['id']},
    )
    assert current.status_code == 200
    assert [item['id'] for item in current.json()['rules']] == [first_rule.json()['id']]

    archive = await client.get(
        f"/api/v1/benefits/olympiad/{ctx[1]['id']}",
        params={'season_id': next_season['id']},
    )
    assert [item['id'] for item in archive.json()['rules']] == [next_rule.json()['id']]


async def test_seasons_list_can_include_archived_with_profiles(client):
    """Архивный сезон сохраняет профили и отдаётся отдельным флагом."""
    await admin_client(client)
    olympiad = await create_olympiad(client, 'Олимпиада с архивом')
    season = await create_season(client, olympiad['id'], '2023/2024')
    await create_profile(client, season['id'], 'Математика', '1')
    archived = await client.put(
        f"/api/v1/seasons/{season['id']}",
        json={'is_archived': True, 'version': season['version']},
    )
    assert archived.status_code == 200, archived.text

    actual = await client.get(f"/api/v1/olympiads/{olympiad['id']}/seasons")
    assert actual.json()['seasons'] == []

    history = await client.get(
        f"/api/v1/olympiads/{olympiad['id']}/seasons",
        params={'include_archived': True, 'profiles': True},
    )
    assert history.status_code == 200
    rows = history.json()['seasons']
    assert len(rows) == 1
    assert rows[0]['is_archived'] is True
    assert rows[0]['profiles'][0]['name'] == 'Математика'


# ------------------------------ Админка ------------------------------


async def test_admin_benefits_filters_needs_review(client):
    """Очередь модерации умеет фильтровать правила, требующие уточнения."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада модерации')
    season = await create_season(client, olympiad['id'])
    profile = await create_profile(client, season['id'])
    doc = await upload_university_doc(client, university['id'])
    created = await _create_rule(client, (university, olympiad, season, profile, doc))
    rule = created.json()

    marked = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={'version': rule['version'], 'needs_review': True},
    )
    assert marked.status_code == 200

    queue = await client.get(
        '/api/v1/admin/benefits', params={'needs_review': True}
    )
    assert queue.status_code == 200
    assert [item['id'] for item in queue.json()['rules']] == [rule['id']]
    assert queue.json()['total'] == 1


async def test_admin_can_see_unpublished_and_rejected(client):
    """Админ-список не прячет черновики и отклонённые правила."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада админа')
    season = await create_season(client, olympiad['id'])
    profile = await create_profile(client, season['id'])
    doc = await upload_university_doc(client, university['id'])

    draft = await _create_rule(
        client, (university, olympiad, season, profile, doc),
        is_published=False,
    )
    assert draft.status_code == 200

    public = await client.get('/api/v1/benefits')
    assert draft.json()['id'] not in [
        item['id'] for item in public.json()['rules']
    ]

    listed = await client.get('/api/v1/admin/benefits')
    assert draft.json()['id'] in [
        item['id'] for item in listed.json()['rules']
    ]


async def test_admin_creates_and_verifies_rule_for_any_university(client):
    """Администратор ведёт правило любого вуза, даже без представителя.

    Иначе новый вуз оставался бы без правил: создавать их мог только
    представитель своего университета, а администратор не мог ни добавить
    правило, ни исправить существующее.
    """
    await admin_client(client)
    own = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'МФТИ')
    olympiad = await create_olympiad(client, 'Олимпиада администратора')
    season = await create_season(client, olympiad['id'])
    profile = await create_profile(client, season['id'])
    doc = await upload_university_doc(client, other['id'])

    created = await client.post(
        f"/api/v1/universities/{other['id']}/benefits",
        json={
            'olympiad_id': olympiad['id'],
            'season_id': season['id'],
            'profile_id': profile['id'],
            'benefit_type': 'BVI',
            'required_result_type': 'WINNER',
            'doc_id': doc['id'],
        },
    )
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule['university_id'] == other['id']
    assert rule['verification_status'] == 'unverified'

    updated = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={
            'version': rule['version'],
            'benefit_type': 'EGE_100',
            'change_reason': 'Правка администратора',
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()['benefit_type'] == 'EGE_100'
    assert updated.json()['verification_status'] == 'unverified'

    verified = await client.post(f"/api/v1/benefits/{rule['id']}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()['verification_status'] == 'verified'

    # Документ-основание чужого вуза не принимается: подтверждение опирается
    # на приказ того университета, чьё это правило.
    foreign_doc = await upload_university_doc(client, own['id'])
    crossed = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={
            'version': verified.json()['version'],
            'doc_id': foreign_doc['id'],
        },
    )
    assert crossed.status_code == 422


async def test_admin_reject_unpublishes_rule_and_keeps_reason(client):
    """Отклонение требует причину и снимает правило с публикации."""
    ctx = await _context(client)
    await admin_client(client)
    created = await _create_rule(client, ctx)
    rule = created.json()

    missing = await client.post(
        f"/api/v1/benefits/{rule['id']}/reject", json={'reason': ''}
    )
    assert missing.status_code in (400, 422)

    rejected = await client.post(
        f"/api/v1/benefits/{rule['id']}/reject",
        json={'reason': 'В приказе нет этой олимпиады'},
    )
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body['verification_status'] == 'rejected'
    assert body['is_published'] is False
    assert body['rejection_reason'] == 'В приказе нет этой олимпиады'


# ------------------------------ Запросы в каталог ------------------------------


async def test_entity_request_approval_creates_season_once(client):
    """Одобрение запроса создаёт сущность один раз; повтор — 409, без дубля."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада запросов')
    await university_rep_client(client, university['id'])

    requested = await client.post(
        f"/api/v1/universities/{university['id']}/entity-requests",
        json={
            'entity_type': 'SEASON',
            'name': '2027/2028',
            'parent_id': olympiad['id'],
        },
    )
    assert requested.status_code == 201, requested.text
    request_id = requested.json()['id']

    # Представитель не создаёт сущность напрямую.
    direct = await client.post(
        f"/api/v1/olympiads/{olympiad['id']}/seasons",
        json={'season_label': '2027/2028'},
    )
    assert direct.status_code == 403

    await admin_client(client)
    approved = await client.post(
        f"/api/v1/admin/entity-requests/{request_id}/approve"
    )
    assert approved.status_code == 200, approved.text
    created_id = approved.json()['entity_id']

    seasons = await client.get(
        f"/api/v1/olympiads/{olympiad['id']}/seasons",
        params={'include_archived': True},
    )
    assert [item['id'] for item in seasons.json()['seasons']].count(created_id) == 1

    again = await client.post(
        f"/api/v1/admin/entity-requests/{request_id}/approve"
    )
    assert again.status_code == 409


async def test_entity_request_rejection_requires_reason(client):
    """Отклонить запрос без причины нельзя: очередь должна объяснять отказ."""
    await admin_client(client)
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])
    requested = await client.post(
        f"/api/v1/universities/{university['id']}/entity-requests",
        json={'entity_type': 'OLYMPIAD', 'name': 'Новая олимпиада'},
    )
    assert requested.status_code == 201

    await admin_client(client)
    empty = await client.post(
        f"/api/v1/admin/entity-requests/{requested.json()['id']}/reject",
        json={'reason': '   '},
    )
    assert empty.status_code in (400, 422)

    rejected = await client.post(
        f"/api/v1/admin/entity-requests/{requested.json()['id']}/reject",
        json={'reason': 'Дубль существующей олимпиады'},
    )
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'rejected'


# ------------------------------ Legacy ------------------------------


async def test_legacy_source_and_program_link_are_gone(client):
    """Программы — самостоятельный справочник; отдельного источника нет."""
    await admin_client(client)
    schema = await client.get('/openapi.json')
    paths = schema.json()['paths']
    assert '/api/v1/admin/sources' not in paths
    assert not [p for p in paths if p.endswith('/sources')]
    assert not [p for p in paths if '/bvi' in p]

    university = await create_university(client, 'Университет ИТМО')
    program = await client.post(
        f"/api/v1/universities/{university['id']}/programs",
        json={'name': 'Прикладная математика', 'code': '01.03.02'},
    )
    assert program.status_code in (200, 201), program.text
    assert 'program_ids' not in program.json()

    listed = await client.get(f"/api/v1/universities/{university['id']}/programs")
    assert listed.status_code == 200
    assert [item['id'] for item in listed.json()['programs']] == [program.json()['id']]


async def test_program_belongs_to_one_university(client):
    """Программа создаётся в справочнике конкретного вуза и не переносится."""
    first = await create_university(client, 'Первый университет')
    second = await create_university(client, 'Второй университет')
    await admin_client(client)

    created = await client.post(
        f"/api/v1/universities/{first['id']}/programs",
        json={'name': 'Математика'},
    )
    assert created.status_code in (200, 201)

    first_list = await client.get(f"/api/v1/universities/{first['id']}/programs")
    second_list = await client.get(f"/api/v1/universities/{second['id']}/programs")
    assert [item['id'] for item in first_list.json()['programs']] == [created.json()['id']]
    assert second_list.json()['programs'] == []
