import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    university_rep_client,
    upload_document,
)


async def test_season_profile_and_program_flow(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')

    # season + profile (admin)
    await admin_client(client)
    season_resp = await client.post(
        f'/api/v1/olympiads/{olympiad["id"]}/seasons',
        json={'season_label': '2025/2026', 'rsosh_level': '1'},
    )
    assert season_resp.status_code in (200, 201), season_resp.text
    season = season_resp.json()
    profile_resp = await client.post(
        f'/api/v1/seasons/{season["id"]}/profiles',
        json={'subject': 'Физика', 'profile_name': 'Физика'},
    )
    assert profile_resp.status_code in (200, 201), profile_resp.text
    profile = profile_resp.json()

    # program under university
    prog_resp = await client.post(
        f'/api/v1/universities/{university["id"]}/programs',
        json={'name': 'Прикладная математика'},
    )
    assert prog_resp.status_code in (200, 201), prog_resp.text
    program = prog_resp.json()

    # benefit rule by rep
    await university_rep_client(client, university['id'])
    rule_resp = await client.post(
        f'/api/v1/universities/{university["id"]}/benefits',
        json={
            'olympiad_id': olympiad['id'],
            'season_id': season['id'],
            'profile_id': profile['id'],
            'benefit_type': 'BVI',
            'subject': 'Физика',
            'program_ids': [program['id']],
            'source_url': 'https://example.com/order',
        },
    )
    assert rule_resp.status_code in (200, 201), rule_resp.text
    rule = rule_resp.json()
    assert rule['verification_status'] == 'unverified'

    # Непроверенное правило не попадает в публичный каталог, но представитель
    # видит его в рабочем списке и может продолжить редактирование.
    public_before = await client.get(
        '/api/v1/benefits',
        params={'university_id': university['id']},
    )
    assert public_before.status_code == 200
    assert public_before.json()['rules'] == []

    managed = await client.get(
        f'/api/v1/universities/{university["id"]}/benefit-rules/manage'
    )
    assert managed.status_code == 200, managed.text
    assert [item['id'] for item in managed.json()['rules']] == [rule['id']]

    # История версий для непроверенного правила доступна через manage-маршрут.
    versions = await client.get(f'/api/v1/benefits/{rule["id"]}/versions/manage')
    assert versions.status_code == 200, versions.text
    assert len(versions.json()['versions']) >= 1

    # Проверку выполняет администратор: ему нужны документ-основание и ссылка
    # на источник. Публичная выдача становится доступной только после проверки.
    await admin_client(client)
    doc = await upload_document(
        client, 'order.pdf', b'%PDF-1.4 fake', doc_type='UNIVERSITY_ORDER'
    )
    attached = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={'doc_id': doc['id']},
    )
    assert attached.status_code == 200, attached.text
    verified = await client.post(f'/api/v1/benefits/{rule["id"]}/verify')
    assert verified.status_code == 200, verified.text
    assert verified.json()['verification_status'] == 'verified'

    # combined filters (публичная выдача после проверки)
    filt = await client.get(
        '/api/v1/benefits',
        params={'university_id': university['id'], 'benefit_type': 'BVI', 'subject': 'Физика', 'program_id': program['id']},
    )
    assert filt.status_code == 200
    assert len(filt.json()['rules']) == 1
    assert filt.json()['rules'][0]['verification_status'] == 'verified'

    versions = await client.get(f'/api/v1/benefits/{rule["id"]}/versions')
    assert versions.status_code == 200
    assert len(versions.json()['versions']) >= 1


async def test_optimistic_concurrency_conflict(client):
    university = await create_university(client, 'Университет МФТИ')
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')
    await university_rep_client(client, university['id'])
    rule_resp = await client.post(
        f'/api/v1/universities/{university["id"]}/benefits',
        json={'olympiad_id': olympiad['id'], 'benefit_type': 'BVI', 'source_url': 'https://example.com'},
    )
    assert rule_resp.status_code in (200, 201)
    rule = rule_resp.json()
    # stale version
    bad = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={'required_result': 'победитель', 'version': 999},
    )
    assert bad.status_code == 409


async def test_rep_application_and_audit(client):
    university = await create_university(client, 'Университет ВШЭ')
    user = await client.post('/api/v1/auth/register', json={
        'name': 'Rep', 'surname': 'User', 'email': 'rep@example.com', 'password': 'StrongPass123!'
    })
    assert user.status_code == 201
    # submit application
    app_resp = await client.post(
        '/api/v1/representative-applications',
        json={'university_id': university['id'], 'justification': 'Я представитель'},
    )
    assert app_resp.status_code in (200, 201), app_resp.text
    application = app_resp.json()

    await admin_client(client)
    review = await client.post(
        f'/api/v1/admin/representative-applications/{application["id"]}/review',
        json={'status': 'approved'},
    )
    assert review.status_code == 200, review.text

    # audit log available
    logs = await client.get('/api/v1/admin/audit', params={'entity_type': 'representative_application'})
    assert logs.status_code == 200


async def test_verified_requires_doc_and_source(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада')
    await university_rep_client(client, university['id'])
    rule_resp = await client.post(
        f'/api/v1/universities/{university["id"]}/benefits',
        json={'olympiad_id': olympiad['id'], 'benefit_type': 'BVI'},
    )
    rule = rule_resp.json()
    # cannot verify without doc/source
    await admin_client(client)
    verify = await client.post(f'/api/v1/benefits/{rule["id"]}/verify')
    assert verify.status_code == 400


async def test_management_access_is_limited_to_own_university(client):
    own = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'Университет МФТИ')
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')

    await university_rep_client(client, own['id'])
    created = await client.post(
        f'/api/v1/universities/{own["id"]}/benefits',
        json={'olympiad_id': olympiad['id'], 'benefit_type': 'BVI'},
    )
    assert created.status_code in (200, 201), created.text
    rule = created.json()

    # Непроверенное правило недоступно публично даже по прямому id.
    client.cookies.clear()
    assert (await client.get(f'/api/v1/benefits/{rule["id"]}')).status_code == 404

    # Представитель другого вуза не видит рабочий список и историю.
    await university_rep_client(client, other['id'])
    denied_list = await client.get(
        f'/api/v1/universities/{own["id"]}/benefit-rules/manage'
    )
    assert denied_list.status_code == 403, denied_list.text
    denied_rule = await client.get(f'/api/v1/benefits/{rule["id"]}/manage')
    assert denied_rule.status_code == 403, denied_rule.text
    denied_history = await client.get(
        f'/api/v1/benefits/{rule["id"]}/versions/manage'
    )
    assert denied_history.status_code == 403, denied_history.text


async def test_edit_content_resets_verified_status(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')
    await admin_client(client)
    program = (
        await client.post(
            f'/api/v1/universities/{university["id"]}/programs',
            json={'name': 'Прикладная математика'},
        )
    ).json()
    doc = await upload_document(
        client, 'order.pdf', b'%PDF-1.4 fake', doc_type='UNIVERSITY_ORDER'
    )

    await university_rep_client(client, university['id'])
    rule = (
        await client.post(
            f'/api/v1/universities/{university["id"]}/benefits',
            json={
                'olympiad_id': olympiad['id'],
                'benefit_type': 'BVI',
                'subject': 'Физика',
                'source_url': 'https://example.com/order',
                'program_ids': [program['id']],
            },
        )
    ).json()

    await admin_client(client)
    await client.patch(f'/api/v1/benefits/{rule["id"]}', json={'doc_id': doc['id']})
    verified = await client.post(f'/api/v1/benefits/{rule["id"]}/verify')
    assert verified.status_code == 200, verified.text
    assert verified.json()['verification_status'] == 'verified'

    # Правка содержания (условия) снимает проверку.
    edited = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={'subject': 'Математика', 'version': verified.json()['version']},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()['verification_status'] == 'unverified'

    # Повторная проверка, затем смена набора программ — тоже содержание.
    again = await client.post(f'/api/v1/benefits/{rule["id"]}/verify')
    assert again.status_code == 200, again.text
    programs_changed = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={'program_ids': [], 'version': again.json()['version']},
    )
    assert programs_changed.status_code == 200, programs_changed.text
    assert programs_changed.json()['verification_status'] == 'unverified'


async def test_pagination_reports_total_in_manage_list(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')
    await university_rep_client(client, university['id'])
    for subject in ('Физика', 'Математика', 'Информатика'):
        created = await client.post(
            f'/api/v1/universities/{university["id"]}/benefits',
            json={
                'olympiad_id': olympiad['id'],
                'benefit_type': 'BVI',
                'subject': subject,
            },
        )
        assert created.status_code in (200, 201), created.text

    first = await client.get(
        f'/api/v1/universities/{university["id"]}/benefit-rules/manage',
        params={'limit': 2, 'offset': 0},
    )
    assert first.status_code == 200, first.text
    assert first.json()['total'] == 3
    assert len(first.json()['rules']) == 2

    second = await client.get(
        f'/api/v1/universities/{university["id"]}/benefit-rules/manage',
        params={'limit': 2, 'offset': 2},
    )
    assert second.status_code == 200, second.text
    assert second.json()['total'] == 3
    assert len(second.json()['rules']) == 1


async def test_representative_document_download_is_own_only(client):
    own = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'Университет МФТИ')

    await university_rep_client(client, own['id'])
    uploaded = await client.post(
        f'/api/v1/universities/{own["id"]}/docs',
        files={'file': ('order.pdf', b'%PDF-1.4 fake', 'application/pdf')},
        data={'type': 'UNIVERSITY_ORDER', 'name': 'Приказ о льготах'},
    )
    assert uploaded.status_code == 201, uploaded.text
    doc = uploaded.json()
    assert doc['university_id'] == own['id']

    own_file = await client.get(f'/api/v1/docs/{doc["id"]}/file')
    assert own_file.status_code == 200, own_file.text

    await university_rep_client(client, other['id'])
    denied = await client.get(f'/api/v1/docs/{doc["id"]}/file')
    assert denied.status_code == 403, denied.text


async def test_archived_olympiad_rejects_new_benefit_rule(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')
    await admin_client(client)
    archived = await client.post(
        f'/api/v1/admin/archive_olympiad/{olympiad["id"]}?archived=true'
    )
    assert archived.status_code == 200, archived.text

    await university_rep_client(client, university['id'])
    created = await client.post(
        f'/api/v1/universities/{university["id"]}/benefits',
        json={'olympiad_id': olympiad['id'], 'benefit_type': 'BVI'},
    )
    assert created.status_code == 400, created.text


async def test_duplicate_season_label_returns_conflict(client):
    olympiad = await create_olympiad(client, 'Олимпиада Физтех')
    await admin_client(client)
    first = await client.post(
        f'/api/v1/olympiads/{olympiad["id"]}/seasons',
        json={'season_label': '2025/2026'},
    )
    assert first.status_code in (200, 201), first.text
    duplicate = await client.post(
        f'/api/v1/olympiads/{olympiad["id"]}/seasons',
        json={'season_label': '2025/2026'},
    )
    assert duplicate.status_code == 409, duplicate.text


async def test_season_and_program_versions_allow_editing(client):
    """Формы правки шлют version: без неё сервер всегда отвечал 409."""
    olympiad = await create_olympiad(client, 'Олимпиада с версиями')
    university = await create_university(client, 'Университет с версиями')
    await admin_client(client)

    season_resp = await client.post(
        f'/api/v1/olympiads/{olympiad["id"]}/seasons',
        json={'season_label': '2024/2025', 'rsosh_level': '1'},
    )
    assert season_resp.status_code in (200, 201), season_resp.text
    season = season_resp.json()
    assert season['version'] == 1

    updated = await client.put(
        f'/api/v1/seasons/{season["id"]}',
        json={
            'season_label': '2024/2025',
            'rsosh_level': '2',
            'version': season['version'],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()['version'] == 2

    stale = await client.put(
        f'/api/v1/seasons/{season["id"]}',
        json={'season_label': '2024/2025', 'version': season['version']},
    )
    assert stale.status_code == 409, stale.text

    program_resp = await client.post(
        f'/api/v1/universities/{university["id"]}/programs',
        json={'name': 'Прикладная информатика', 'code': '09.03.03'},
    )
    assert program_resp.status_code in (200, 201), program_resp.text
    program = program_resp.json()
    assert program['version'] == 1

    program_updated = await client.put(
        f'/api/v1/programs/{program["id"]}',
        json={'name': 'Прикладная информатика', 'description': 'Новое описание', 'version': program['version']},
    )
    assert program_updated.status_code == 200, program_updated.text
    assert program_updated.json()['version'] == 2

    program_stale = await client.put(
        f'/api/v1/programs/{program["id"]}',
        json={'name': 'Прикладная информатика', 'version': program['version']},
    )
    assert program_stale.status_code == 409, program_stale.text


async def test_season_and_program_reference_validation(client):
    await admin_client(client)
    missing_olympiad = await client.post(
        f'/api/v1/olympiads/{uuid.uuid4()}/seasons',
        json={'season_label': '2025/2026'},
    )
    assert missing_olympiad.status_code == 404, missing_olympiad.text

    university = await create_university(client, 'Университет проверок')
    await admin_client(client)
    missing_university = await client.post(
        f'/api/v1/universities/{uuid.uuid4()}/programs',
        json={'name': 'Программа'},
    )
    assert missing_university.status_code == 404, missing_university.text

    first = await client.post(
        f'/api/v1/universities/{university["id"]}/programs',
        json={'name': 'Одинаковая программа'},
    )
    assert first.status_code in (200, 201), first.text
    duplicate = await client.post(
        f'/api/v1/universities/{university["id"]}/programs',
        json={'name': 'Одинаковая программа'},
    )
    assert duplicate.status_code == 409, duplicate.text


async def test_rep_application_is_visible_and_not_duplicated(client):
    university = await create_university(client, 'Университет заявок')
    email = f'rep-{uuid.uuid4().hex}@example.com'
    registered = await client.post('/api/v1/auth/register', json={
        'name': 'Иван',
        'surname': 'Представителев',
        'email': email,
        'password': 'StrongPass123!',
    })
    assert registered.status_code == 201, registered.text

    first = await client.post(
        '/api/v1/representative-applications',
        json={'university_id': university['id'], 'justification': 'Я сотрудник вуза'},
    )
    assert first.status_code in (200, 201), first.text
    application = first.json()

    second = await client.post(
        '/api/v1/representative-applications',
        json={'university_id': university['id'], 'justification': 'Повторно'},
    )
    assert second.status_code in (200, 201), second.text
    assert second.json()['id'] == application['id'], 'повторная заявка создала дубль'

    mine = await client.get('/api/v1/applications/my')
    assert mine.status_code == 200, mine.text
    my_apps = mine.json()['applications']
    assert [item['id'] for item in my_apps] == [application['id']]

    await admin_client(client)
    listed = await client.get('/api/v1/admin/representative-applications')
    assert listed.status_code == 200, listed.text
    rows = listed.json()['applications']
    row = next(item for item in rows if item['id'] == application['id'])
    assert row['user_email'] == email
    assert row['user_name'] == 'Иван Представителев'
    assert row['university_name'] == 'Университет заявок'

    invalid = await client.post(
        f'/api/v1/admin/representative-applications/{application["id"]}/review',
        json={'status': 'maybe'},
    )
    assert invalid.status_code == 400, invalid.text

    approved = await client.post(
        f'/api/v1/admin/representative-applications/{application["id"]}/review',
        json={'status': 'approved'},
    )
    assert approved.status_code == 200, approved.text

    # Фильтры аудита: действие и тип сущности сужают выборку, а total считает
    # записи под фильтром, а не размер страницы.
    filtered = await client.get(
        '/api/v1/admin/audit',
        params={
            'entity_type': 'representative_application',
            'action': 'review',
        },
    )
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert payload['total'] >= 1
    assert payload['logs']
    assert all(item['action'] == 'review' for item in payload['logs'])
    assert all(
        item['entity_type'] == 'representative_application'
        for item in payload['logs']
    )

    none = await client.get('/api/v1/admin/audit', params={'action': 'no-such-action'})
    assert none.status_code == 200, none.text
    assert none.json() == {'logs': [], 'total': 0}


async def test_olympiad_organizer_is_saved_and_public(client):
    olympiad = await create_olympiad(
        client, 'Олимпиада с организатором', organizer='МФТИ'
    )
    assert olympiad['organizer'] == 'МФТИ'

    public = await client.get(f'/api/v1/olympiads/{olympiad["id"]}')
    assert public.status_code == 200, public.text
    assert public.json()['organizer'] == 'МФТИ'

    catalog = await client.get('/api/v1/olympiads')
    row = next(
        item for item in catalog.json()['olympiads']
        if item['id'] == olympiad['id']
    )
    assert row['organizer'] == 'МФТИ'

    await admin_client(client)
    edited = await client.post(
        f'/api/v1/olympiads/edit_olympiad/{olympiad["id"]}',
        json={'organizer': 'Минобрнауки России'},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()['organizer'] == 'Минобрнауки России'

    cleared = await client.post(
        f'/api/v1/olympiads/edit_olympiad/{olympiad["id"]}',
        json={'organizer': ''},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()['organizer'] is None


async def test_benefit_publication_toggle_keeps_verification(client):
    """Скрытие из каталога не снимает проверку и не требует новой модерации."""
    university = await create_university(client, 'Университет публикаций')
    olympiad = await create_olympiad(client, 'Олимпиада публикаций')
    await admin_client(client)
    doc = await upload_document(
        client, 'order.pdf', b'%PDF-1.4 fake', doc_type='UNIVERSITY_ORDER'
    )

    await university_rep_client(client, university['id'])
    created = await client.post(
        f'/api/v1/universities/{university["id"]}/benefits',
        json={
            'olympiad_id': olympiad['id'],
            'benefit_type': 'BVI',
            'source_url': 'https://example.com/order',
        },
    )
    assert created.status_code in (200, 201), created.text
    rule = created.json()
    assert rule['is_published'] is True

    await admin_client(client)
    attached = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={'doc_id': doc['id']},
    )
    assert attached.status_code == 200, attached.text
    verified = await client.post(f'/api/v1/benefits/{rule["id"]}/verify')
    assert verified.status_code == 200, verified.text
    verified_rule = verified.json()

    public = await client.get(
        '/api/v1/benefits', params={'university_id': university['id']}
    )
    assert [item['id'] for item in public.json()['rules']] == [rule['id']]

    hidden = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={
            'is_published': False,
            'version': verified_rule['version'],
        },
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()['is_published'] is False
    assert hidden.json()['verification_status'] == 'verified', (
        'переключение публикации не должно снимать проверку'
    )

    public_after = await client.get(
        '/api/v1/benefits', params={'university_id': university['id']}
    )
    assert public_after.json()['rules'] == []
    assert public_after.json()['total'] == 0
    direct = await client.get(f'/api/v1/benefits/{rule["id"]}')
    assert direct.status_code == 404, direct.text

    managed = await client.get(f'/api/v1/benefits/{rule["id"]}/manage')
    assert managed.status_code == 200, managed.text
    assert managed.json()['is_published'] is False
    assert managed.json()['verification_status'] == 'verified'

    shown = await client.patch(
        f'/api/v1/benefits/{rule["id"]}',
        json={
            'is_published': True,
            'version': hidden.json()['version'],
        },
    )
    assert shown.status_code == 200, shown.text
    public_again = await client.get(
        '/api/v1/benefits', params={'university_id': university['id']}
    )
    assert [item['id'] for item in public_again.json()['rules']] == [rule['id']]


async def test_source_crud_and_representative_visibility(client):
    university = await create_university(client, 'Университет источников')
    other = await create_university(client, 'Другой университет источников')
    await admin_client(client)

    global_source = (
        await client.post(
            '/api/v1/admin/sources',
            json={
                'name': 'Перечень олимпиад РСОШ',
                'kind': 'RSOSH_LIST',
                'url': 'https://example.com/rsosh',
            },
        )
    )
    assert global_source.status_code == 201, global_source.text
    global_source = global_source.json()
    assert global_source['university_id'] is None

    own = (
        await client.post(
            '/api/v1/admin/sources',
            json={
                'name': 'Приказ университета источников',
                'kind': 'UNIVERSITY_ORDER',
                'university_id': university['id'],
            },
        )
    ).json()
    foreign = (
        await client.post(
            '/api/v1/admin/sources',
            json={
                'name': 'Чужой приказ',
                'kind': 'UNIVERSITY_ORDER',
                'university_id': other['id'],
            },
        )
    ).json()

    listed = await client.get('/api/v1/admin/sources')
    assert listed.status_code == 200, listed.text
    assert listed.json()['total'] == 3

    filtered = await client.get(
        '/api/v1/admin/sources', params={'university_id': university['id']}
    )
    assert filtered.json()['total'] == 1
    assert filtered.json()['sources'][0]['id'] == own['id']

    assert (
        await client.post(
            '/api/v1/admin/sources',
            json={'name': 'Без вуза', 'university_id': str(uuid.uuid4())},
        )
    ).status_code == 400
    assert (
        await client.post(
            '/api/v1/admin/sources',
            json={'name': 'Неизвестный тип', 'kind': 'BOGUS'},
        )
    ).status_code == 422
    assert (
        await client.post('/api/v1/admin/sources', json={'name': '   '})
    ).status_code == 422

    # Представителю видны общие источники и источники своего вуза, но не чужие.
    await university_rep_client(client, university['id'])
    available = await client.get(
        f'/api/v1/universities/{university["id"]}/sources'
    )
    assert available.status_code == 200, available.text
    ids = {item['id'] for item in available.json()['sources']}
    assert global_source['id'] in ids
    assert own['id'] in ids
    assert foreign['id'] not in ids

    denied = await client.post('/api/v1/admin/sources', json={'name': 'Нельзя'})
    assert denied.status_code == 403, denied.text

    # Правило со ссылкой на источник: после удаления источника оно остаётся,
    # теряя только source_id.
    olympiad = await create_olympiad(client, 'Олимпиада источников')
    await university_rep_client(client, university['id'])
    rule = (
        await client.post(
            f'/api/v1/universities/{university["id"]}/benefits',
            json={
                'olympiad_id': olympiad['id'],
                'benefit_type': 'BVI',
                'source_id': own['id'],
                'source_url': 'https://example.com/order',
            },
        )
    )
    assert rule.status_code in (200, 201), rule.text
    rule = rule.json()
    assert rule['source_id'] == own['id']

    await admin_client(client)
    deleted = await client.delete(f'/api/v1/admin/sources/{own["id"]}')
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()['deleted'] is True

    managed = await client.get(f'/api/v1/benefits/{rule["id"]}/manage')
    assert managed.status_code == 200, managed.text
    assert managed.json()['source_id'] is None
    assert managed.json()['source_url'] == 'https://example.com/order'

    gone = await client.delete(f'/api/v1/admin/sources/{own["id"]}')
    assert gone.status_code == 404, gone.text
