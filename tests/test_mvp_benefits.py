"""MVP-расширение: виды льгот, проверка, сезоны, заявки, версии.

Покрывает требования ТЗ, добавленные поверх базовой модели:
виды льгот и их правка (§4.3), независимый статус проверки (§7.1),
подтверждение со стороны вуза, фильтры и постраничная выдача (§4.5, §10.1),
сезоны и профили (§4.2, §4.4), заявки представителя (§3.4),
версионирование правил с откатом (§8) и доступность документа (§7.3).
"""

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    moderate_bvi,
    register_user,
    upload_document,
    university_rep_client,
)


async def _confirmed_link(client, university, olympiad, benefit_type=None):
    rep = await university_rep_client(client, university['id'])
    created = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert created.status_code == 201, created.text
    await admin_client(client)
    confirmed = await moderate_bvi(client, university['id'], olympiad['id'], 'confirm')
    assert confirmed.status_code == 200, confirmed.text
    if benefit_type:
        updated = await client.put(
            f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
            json={'benefit_type': benefit_type},
        )
        assert updated.status_code == 200, updated.text
    return rep


# --- §4.3 Вид льготы и §7.1 Проверка ---------------------------------------


async def test_benefit_type_and_verification_default_to_bvi_unverified(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    page = await client.get(f"/api/v1/universities/{university['id']}/benefit-rules")
    assert page.status_code == 200, page.text
    rules = page.json()['rules']
    assert len(rules) == 1
    assert rules[0]['benefit_type'] == 'BVI'
    assert rules[0]['verification_status'] == 'unverified'


async def test_benefit_type_validation_rejects_unknown_value(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    bad = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={'benefit_type': 'NONSENSE'},
    )
    assert bad.status_code == 422, bad.text


async def test_admin_can_set_benefit_type_and_verify(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    updated = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={
            'benefit_type': 'EGE_100',
            'result_requirement': 'winner',
            'subject': 'Математика',
            'verification_status': 'verified',
            'reason': 'Сверено с приказом вуза',
        },
    )
    assert updated.status_code == 200, updated.text
    rule = updated.json()['rule']
    assert rule['benefit_type'] == 'EGE_100'
    assert rule['verification_status'] == 'verified'
    assert rule['verified_by'] is not None
    assert rule['verified_at'] is not None


async def test_unverified_link_is_still_listed_with_status(client):
    """Непроверенная связь видна в каталоге — с отдельным статусом."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    page = await client.get(
        f"/api/v1/universities/{university['id']}/olympiads"
    )
    olympiads = page.json()['olympiads']
    assert len(olympiads) == 1
    assert olympiads[0]['verification_status'] == 'unverified'
    assert olympiads[0]['benefit_type'] == 'BVI'


async def test_university_confirmation_is_separate_from_verification(client):
    """Подтверждение вузом ≠ проверка Papaya."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    await university_rep_client(client, university['id'])
    confirmed = await client.post(
        f"/api/v1/universities/{university['id']}/benefit-rules/"
        f"{olympiad['id']}/university-confirmation",
        json={'confirmed': True},
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body['university_confirmed'] is True
    # Проверка Papaya остаётся независимой характеристикой.
    assert body['verification_status'] == 'unverified'


# --- §8 Версионирование и откат --------------------------------------------


async def test_benefit_rule_versions_recorded_and_rollback(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    first = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={'benefit_type': 'EGE_100'},
    )
    assert first.status_code == 200
    assert first.json()['version'] == 1

    second = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={'benefit_type': 'DVI_100', 'reason': 'изменение приказа'},
    )
    assert second.status_code == 200
    assert second.json()['version'] == 2

    history = await client.get(
        f"/api/v1/universities/{university['id']}/benefit-rules/"
        f"{olympiad['id']}/versions"
    )
    assert history.status_code == 200
    versions = history.json()['versions']
    assert [v['version'] for v in versions] == [1, 2]

    rollback = await client.post(
        f"/api/v1/universities/{university['id']}/benefit-rules/"
        f"{olympiad['id']}/rollback/1"
    )
    assert rollback.status_code == 200, rollback.text
    rule = rollback.json()['rule']
    assert rule['benefit_type'] == 'EGE_100'
    assert rollback.json()['version'] == 3

    history2 = await client.get(
        f"/api/v1/universities/{university['id']}/benefit-rules/"
        f"{olympiad['id']}/versions"
    )
    versions2 = history2.json()['versions']
    assert len(versions2) == 3
    assert versions2[-1]['is_rollback'] is True


async def test_benefit_rule_update_requires_admin(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)
    await register_user(client)

    forbidden = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={'benefit_type': 'EGE_100'},
    )
    assert forbidden.status_code == 403


async def test_valid_until_survives_version_snapshot_and_rollback(client):
    """Дата действия правила переживает версионирование и откат.

    Снимок версии уходит в JSONB, поэтому дата хранится строкой и при откате
    разбирается обратно в дату: иначе в колонку ``DATE`` уехала бы строка, а
    откат возвращал бы не тот тип.
    """
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    first = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={'valid_until': '2027-06-01', 'benefit_type': 'EGE_100'},
    )
    assert first.status_code == 200, first.text
    assert first.json()['rule']['valid_until'].startswith('2027-06-01')

    second = await client.put(
        f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
        json={'benefit_type': 'DVI_100'},
    )
    assert second.status_code == 200, second.text

    rollback = await client.post(
        f"/api/v1/universities/{university['id']}/benefit-rules/"
        f"{olympiad['id']}/rollback/1"
    )
    assert rollback.status_code == 200, rollback.text
    rule = rollback.json()['rule']
    assert rule['benefit_type'] == 'EGE_100'
    assert rule['valid_until'].startswith('2027-06-01')


# --- §4.5 Фильтры и §10.1 Пагинация ----------------------------------------


async def test_filters_by_benefit_type_and_subject(client):
    university = await create_university(client, 'Университет ИТМО')
    o1 = await create_olympiad(client, 'Олимпиада «Альфа»')
    o2 = await create_olympiad(client, 'Олимпиада «Бета»')
    await _confirmed_link(client, university, o1, benefit_type='BVI')
    await _confirmed_link(client, university, o2, benefit_type='EGE_100')

    filtered = await client.get(
        f"/api/v1/universities/{university['id']}/benefit-rules",
        params={'benefit_type': 'EGE_100'},
    )
    assert filtered.status_code == 200
    rules = filtered.json()['rules']
    assert [r['olympiad_id'] for r in rules] == [o2['id']]
    assert filtered.json()['total'] == 1


async def test_public_lists_report_total_and_paginate(client):
    await create_university(client, 'Университет ИТМО')
    await create_university(client, 'МФТИ')
    for name in ('Олимпиада «Альфа»', 'Олимпиада «Бета»', 'Олимпиада «Гамма»'):
        await create_olympiad(client, name)

    unis = await client.get('/api/v1/universities', params={'limit': 1})
    assert unis.json()['total'] == 2
    assert len(unis.json()['universities']) == 1

    olympiads = await client.get('/api/v1/olympiads', params={'limit': 2})
    assert olympiads.json()['total'] == 3
    assert len(olympiads.json()['olympiads']) == 2


async def test_subject_filter_applies_before_pagination(client):
    """Фильтр по предмету отсекает строки до постраничной выдачи.

    Если фильтровать после выборки страницы, то страница ``limit=1`` без
    нужного предмета отдала бы пустой список, хотя правило с таким предметом
    есть. Проверяем и состав выдачи, и ``total``.
    """
    university = await create_university(client, 'Университет ИТМО')
    physics = await create_olympiad(client, 'Олимпиада «Физика»')
    math = await create_olympiad(client, 'Олимпиада «Математика»')
    await _confirmed_link(client, university, physics)
    await _confirmed_link(client, university, math)

    for olympiad, subject in ((physics, 'Физика'), (math, 'Математика')):
        await client.put(
            f"/api/v1/universities/{university['id']}/benefit-rules/{olympiad['id']}",
            json={'subject': subject},
        )

    filtered = await client.get(
        f"/api/v1/universities/{university['id']}/benefit-rules",
        params={'subject': 'Математика', 'limit': 1},
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    assert [r['subject'] for r in body['rules']] == ['Математика']
    assert body['total'] == 1


# --- §4.2, §4.4 Сезоны и профили -------------------------------------------


async def test_create_and_list_season_with_profiles(client):
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')

    created = await client.put(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/2026",
        json={'year': 2026, 'state': 'upcoming', 'rsoh_level': '1'},
    )
    assert created.status_code == 200, created.text
    season = created.json()
    assert season['year'] == 2026
    assert season['state'] == 'upcoming'

    profile = await client.post(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/{season['id']}/profiles",
        json={'name': 'Математика', 'subject': 'Математика'},
    )
    assert profile.status_code == 201, profile.text

    listing = await client.get(f"/api/v1/olympiads/{olympiad['id']}/seasons")
    assert listing.status_code == 200
    assert len(listing.json()['seasons']) == 1
    # Профили едут вместе с сезоном: публичная страница олимпиады показывает
    # их без отдельного запроса.
    assert [p['name'] for p in listing.json()['seasons'][0]['profiles']] == [
        'Математика'
    ]

    details = await client.get(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/{season['id']}"
    )
    assert details.status_code == 200
    assert [p['name'] for p in details.json()['profiles']] == ['Математика']


async def test_season_without_dates_is_reported_as_unpublished(client):
    """Сезон без дат: интерфейс показывает «даты не опубликованы» → dates=null."""
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    created = await client.put(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/2026",
        json={'year': 2026},
    )
    assert created.status_code == 200
    assert created.json()['dates'] is None
    assert created.json()['state'] == 'unknown'


async def test_archive_season(client):
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    created = await client.put(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/2025",
        json={'year': 2025, 'state': 'active'},
    )
    season_id = created.json()['id']
    archived = await client.post(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/{season_id}/archive"
    )
    assert archived.status_code == 200
    assert archived.json()['state'] == 'completed'


async def test_season_state_validation(client):
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    bad = await client.put(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/2026",
        json={'year': 2026, 'state': 'nonsense'},
    )
    assert bad.status_code == 422


# --- §3.4 Заявки представителя ---------------------------------------------


async def test_application_flow_approve_grants_rep_role(client):
    from tests.conftest import login_user

    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада «Тест»')

    applicant = await register_user(client)
    submitted = await client.post(
        '/api/v1/applications',
        json={'university_id': university['id'], 'motivation': 'Я сотрудник вуза'},
    )
    assert submitted.status_code == 201, submitted.text
    application = submitted.json()
    assert application['status'] == 'PENDING'

    mine = await client.get('/api/v1/applications/mine')
    assert mine.status_code == 200
    assert len(mine.json()['applications']) == 1

    await admin_client(client)
    queue = await client.get('/api/v1/applications')
    assert queue.status_code == 200
    assert len(queue.json()['applications']) == 1

    decided = await client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={'decision': 'APPROVED', 'note': 'Подтверждено'},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()['status'] == 'APPROVED'

    # Роль выдана: пользователь теперь может управлять связями своего вуза.
    await login_user(client, applicant['email'])
    request = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert request.status_code == 201, request.text


async def test_application_reject(client):
    university = await create_university(client, 'Университет ИТМО')
    await register_user(client)
    submitted = await client.post(
        '/api/v1/applications',
        json={'university_id': university['id']},
    )
    application_id = submitted.json()['id']

    await admin_client(client)
    decided = await client.post(
        f"/api/v1/applications/{application_id}/decision",
        json={'decision': 'REJECTED', 'note': 'Нет подтверждения'},
    )
    assert decided.status_code == 200
    assert decided.json()['status'] == 'REJECTED'
    assert decided.json()['decision_note'] == 'Нет подтверждения'


async def test_application_stays_pending_when_role_cannot_be_granted(client):
    """Одобрение не должно оставлять заявку одобренной без представителя.

    Заявитель — единственный активный администратор, поэтому его понижение до
    представителя запрещено инвариантом «последний администратор». Заявка в
    таком случае обязана остаться в ожидании, а не «одобряться» без роли.
    """
    from sqlalchemy import update

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users
    from tests.conftest import _redis_client

    university = await create_university(client, 'Университет ИТМО')
    applicant = await register_user(client)
    async with AsyncSessionLocal() as session:
        await session.execute(update(Users).values(role='USER'))
        await session.execute(
            update(Users).where(Users.id == applicant['id']).values(role='ADMIN')
        )
        await session.commit()
    _redis_client().flushdb()

    submitted = await client.post(
        '/api/v1/applications',
        json={'university_id': university['id']},
    )
    assert submitted.status_code == 201, submitted.text
    application = submitted.json()

    decided = await client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={'decision': 'APPROVED'},
    )
    assert decided.status_code == 409, decided.text

    mine = await client.get('/api/v1/applications/mine')
    assert mine.status_code == 200, mine.text
    statuses = [item['status'] for item in mine.json()['applications']]
    assert statuses == ['PENDING']

    # Роль тоже не изменилась: администратор остался администратором.
    profile = await client.get(f"/api/v1/user/{applicant['id']}")
    assert profile.status_code == 200, profile.text
    assert profile.json()['role'] == 'ADMIN'


async def test_double_application_conflicts(client):
    university = await create_university(client, 'Университет ИТМО')
    await register_user(client)
    first = await client.post(
        '/api/v1/applications',
        json={'university_id': university['id']},
    )
    assert first.status_code == 201
    second = await client.post(
        '/api/v1/applications',
        json={'university_id': university['id']},
    )
    assert second.status_code == 409


async def test_application_decision_twice_conflicts(client):
    university = await create_university(client, 'Университет ИТМО')
    await register_user(client)
    submitted = await client.post(
        '/api/v1/applications',
        json={'university_id': university['id']},
    )
    application_id = submitted.json()['id']
    await admin_client(client)
    first = await client.post(
        f"/api/v1/applications/{application_id}/decision",
        json={'decision': 'REJECTED'},
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/v1/applications/{application_id}/decision",
        json={'decision': 'APPROVED'},
    )
    assert second.status_code == 409


async def test_application_queue_total_counts_all_not_only_page(client):
    """``total`` в очереди — общее число заявок, а не число строк страницы."""
    university = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'МФТИ')
    for target in (university, other):
        await register_user(client)
        submitted = await client.post(
            '/api/v1/applications',
            json={'university_id': target['id']},
        )
        assert submitted.status_code == 201, submitted.text

    await admin_client(client)
    queue = await client.get('/api/v1/applications', params={'limit': 1})
    assert queue.status_code == 200, queue.text
    body = queue.json()
    assert len(body['applications']) == 1
    assert body['total'] == 2


# --- §7.3 Доступность документа --------------------------------------------


async def test_document_availability_status(client):
    await admin_client(client)
    doc = await upload_document(client, 'r.pdf', b'%PDF-1.4 test', name='Перечень')

    updated = await client.post(
        f"/api/v1/docs/{doc['id']}/availability",
        json={'availability': 'broken'},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()['availability'] == 'broken'
    assert updated.json()['availability_checked_at'] is not None

    details = await client.get(f"/api/v1/docs/{doc['id']}")
    assert details.json()['availability'] == 'broken'

    bad = await client.post(
        f"/api/v1/docs/{doc['id']}/availability",
        json={'availability': 'nonsense'},
    )
    assert bad.status_code == 422


# --- §4.1 Образовательные программы -----------------------------------------


async def test_programs_are_public_and_managed_by_university_rep(client):
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])

    listed = await client.get(f"/api/v1/universities/{university['id']}/programs")
    assert listed.status_code == 200, listed.text
    assert listed.json()['programs'] == []
    assert listed.json()['total'] == 0

    saved = await client.put(
        f"/api/v1/universities/{university['id']}/programs",
        json={'programs': ['Прикладная математика', 'Лингвистика', 'Прикладная математика']},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body['total'] == 2
    # Порядок задаёт сервер — по нормализованному имени, по алфавиту.
    assert sorted(item['name'] for item in body['programs']) == [
        'Лингвистика',
        'Прикладная математика',
    ]

    public = await client.get(f"/api/v1/universities/{university['id']}/programs")
    assert public.status_code == 200, public.text
    assert public.json()['total'] == 2


async def test_programs_of_other_university_are_protected(client):
    university = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'МФТИ')
    await university_rep_client(client, university['id'])

    denied = await client.put(
        f"/api/v1/universities/{other['id']}/programs",
        json={'programs': ['Чужое направление']},
    )
    assert denied.status_code == 403, denied.text

    other_listed = await client.get(f"/api/v1/universities/{other['id']}/programs")
    assert other_listed.json()['total'] == 0
