"""Правило льготы как отдельная сущность: каталог, права, проверка, версии.

Главный сценарий Papaya: университет показывает олимпиады с условиями льгот,
олимпиада — университеты, которые её принимают. Представитель вуза заводит
правила по существующим олимпиадам, администратор проверяет их. Здесь
собраны сквозные сценарии ТЗ: видимость (черновик/публикация/архив/отклонено),
фильтры, права, версии и оптимистичная блокировка, политика проверки,
документ, журнал аудита, заявки на каталог.
"""

import asyncio
import uuid

from httpx import ASGITransport, AsyncClient

from tests.conftest import (
    admin_client,
    create_benefit_rule,
    create_olympiad,
    create_university,
    login_user,
    register_user,
    university_rep_client,
)

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n'


def _anon():
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver')


async def _season(client, olympiad_id, year=2026, **fields):
    response = await client.put(
        f'/api/v1/olympiads/{olympiad_id}/seasons/{year}', json=fields
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _profile(client, olympiad_id, season_id, name='Математика'):
    response = await client.post(
        f'/api/v1/olympiads/{olympiad_id}/seasons/{season_id}/profiles',
        json={'name': name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _program(client, university_id, name='Прикладная математика'):
    response = await client.post(
        f'/api/v1/universities/{university_id}/programs', json={'name': name}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _setup(client, *, publish=True, **rule_fields):
    """Вуз, опубликованная олимпиада, представитель и одно правило от него."""
    university = await create_university(client, 'Университет ИТМО', short_name='ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    rep = await university_rep_client(client, university['id'])
    rule = await create_benefit_rule(
        client, university['id'], olympiad['id'], publish=publish, **rule_fields
    )
    return university, olympiad, rep, rule


def _rules_url(university, rule_id=None):
    base = f"/api/v1/universities/{university['id']}/benefit-rules"
    return f'{base}/{rule_id}' if rule_id else base


# --- Публичный каталог -------------------------------------------------------


async def test_published_rule_is_visible_on_both_sides(client):
    university, olympiad, _rep, rule = await _setup(client)

    async with _anon() as anon:
        page = await anon.get(f"/api/v1/universities/{university['id']}/olympiads")
        assert page.status_code == 200, page.text
        olympiads = page.json()['olympiads']
        assert [item['id'] for item in olympiads] == [olympiad['id']]
        assert [r['id'] for r in olympiads[0]['rules']] == [rule['id']]
        assert olympiads[0]['rules'][0]['verification_status'] == 'unverified'

        back = await anon.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
        assert back.status_code == 200, back.text
        universities = back.json()['universities']
        assert [item['id'] for item in universities] == [university['id']]
        assert universities[0]['rules'][0]['id'] == rule['id']

        detail = await anon.get(f"/api/v1/benefit-rules/{rule['id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()['university_name'] == 'Университет ИТМО'
        assert detail.json()['olympiad_name'] == olympiad['name']


async def test_draft_is_hidden_from_public_but_visible_to_owner(client):
    university, olympiad, _rep, rule = await _setup(client, publish=False)
    assert rule['status'] == 'draft'

    # Представитель видит свой черновик.
    mine = await client.get(_rules_url(university), params={'include_drafts': 'true'})
    assert mine.status_code == 200, mine.text
    assert [r['id'] for r in mine.json()['rules']] == [rule['id']]

    async with _anon() as anon:
        public = await anon.get(f"/api/v1/universities/{university['id']}/olympiads")
        assert public.json()['olympiads'] == []
        assert public.json()['total'] == 0
        flat = await anon.get(_rules_url(university))
        assert flat.json()['total'] == 0
        detail = await anon.get(f"/api/v1/benefit-rules/{rule['id']}")
        assert detail.status_code == 404
        back = await anon.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
        assert back.json()['universities'] == []
        drafts = await anon.get(_rules_url(university), params={'include_drafts': 'true'})
        assert drafts.status_code == 401


async def test_filters_combine_and_apply_before_pagination(client):
    university = await create_university(client, 'Университет ИТМО')
    physics = await create_olympiad(client, 'Олимпиада «Физика»')
    math = await create_olympiad(client, 'Олимпиада «Математика»')
    await admin_client(client)
    pm = await _program(client, university['id'], 'Прикладная математика')
    ph = await _program(client, university['id'], 'Физика')
    await university_rep_client(client, university['id'])
    r_math = await create_benefit_rule(
        client, university['id'], math['id'],
        benefit_type='BVI', subject='Математика', program_ids=[pm['id']],
    )
    await create_benefit_rule(
        client, university['id'], physics['id'],
        benefit_type='EGE_100', subject='Физика', program_ids=[ph['id']],
    )
    await create_benefit_rule(
        client, university['id'], physics['id'],
        benefit_type='BVI', subject='Физика', program_ids=[pm['id'], ph['id']],
    )

    async with _anon() as anon:
        url = f"/api/v1/universities/{university['id']}/olympiads"
        by_type = await anon.get(url, params={'benefit_type': 'EGE_100'})
        assert [o['id'] for o in by_type.json()['olympiads']] == [physics['id']]
        assert len(by_type.json()['olympiads'][0]['rules']) == 1

        combined = await anon.get(
            url, params={'benefit_type': 'BVI', 'program_id': pm['id'], 'subject': 'математика'}
        )
        assert [o['id'] for o in combined.json()['olympiads']] == [math['id']]
        assert combined.json()['total'] == 1

        # Фильтр по программе: два правила с «Прикладная математика», limit=1.
        paged = await anon.get(_rules_url(university), params={'program_id': pm['id'], 'limit': 1})
        assert paged.json()['total'] == 2
        assert len(paged.json()['rules']) == 1

        facets = await anon.get(_rules_url(university) + '/facets')
        assert facets.status_code == 200, facets.text
        body = facets.json()
        assert {f['value']: f['count'] for f in body['benefit_types']} == {'BVI': 2, 'EGE_100': 1}
        assert {f['id']: f['count'] for f in body['programs']} == {pm['id']: 2, ph['id']: 2}

        bad = await anon.get(url, params={'benefit_type': 'NONSENSE'})
        assert bad.status_code == 422

        oly_side = await anon.get(
            f"/api/v1/olympiads/{physics['id']}/universities",
            params={'benefit_type': 'BVI', 'subject': 'Физика'},
        )
        assert oly_side.json()['total'] == 1
        assert [r['benefit_type'] for r in oly_side.json()['universities'][0]['rules']] == ['BVI']
        assert r_math['id'] not in [
            r['id'] for u in oly_side.json()['universities'] for r in u['rules']
        ]


async def test_season_and_profile_are_attached_and_archived_season_stays(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада «Физтех»')
    season = await _season(client, olympiad['id'], 2026, label='2025/26', rsoh_level='1')
    profile = await _profile(client, olympiad['id'], season['id'])
    other_season = await _season(client, olympiad['id'], 2025)
    await university_rep_client(client, university['id'])

    wrong = await client.post(
        _rules_url(university),
        json={
            'olympiad_id': olympiad['id'],
            'season_id': other_season['id'],
            'profile_id': profile['id'],
        },
    )
    assert wrong.status_code == 400, wrong.text

    rule = await create_benefit_rule(
        client, university['id'], olympiad['id'],
        season_id=season['id'], profile_id=profile['id'],
    )
    assert rule['season']['label'] == '2025/26'
    assert rule['profile']['name'] == 'Математика'

    # Архив сезона — состояние сезона, не правила (ТЗ: статусы независимы).
    await admin_client(client)
    archived = await client.post(
        f"/api/v1/olympiads/{olympiad['id']}/seasons/{season['id']}/archive"
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()['state'] == 'completed'
    async with _anon() as anon:
        detail = await anon.get(f"/api/v1/benefit-rules/{rule['id']}")
        assert detail.json()['status'] == 'published'
        assert detail.json()['season']['state'] == 'completed'
        filtered = await anon.get(
            f"/api/v1/universities/{university['id']}/olympiads",
            params={'season_id': season['id']},
        )
        assert filtered.json()['total'] == 1
        seasons = await anon.get(f"/api/v1/olympiads/{olympiad['id']}/seasons")
        assert [s['year'] for s in seasons.json()['seasons']] == [2026, 2025]
        assert seasons.json()['seasons'][0]['dates'] is None


async def test_archived_olympiad_keeps_rules_as_historical(client):
    university, olympiad, _rep, rule = await _setup(client)
    await admin_client(client)
    archived = await client.post(f"/api/v1/admin/archive_olympiad/{olympiad['id']}")
    assert archived.status_code == 200, archived.text
    assert archived.json()['status'] == 'ARCHIVED'

    async with _anon() as anon:
        detail = await anon.get(f"/api/v1/benefit-rules/{rule['id']}")
        assert detail.status_code == 200
        assert detail.json()['is_historical'] is True

    await university_rep_client(client, university['id'])
    again = await client.post(_rules_url(university), json={'olympiad_id': olympiad['id']})
    assert again.status_code == 409, again.text


# --- Права -------------------------------------------------------------------


async def test_anonymous_and_plain_user_cannot_manage_rules(client):
    university, _olympiad, _rep, rule = await _setup(client)
    olympiad2 = await create_olympiad(client, 'Олимпиада «Бета»')

    async with _anon() as anon:
        created = await anon.post(_rules_url(university), json={'olympiad_id': olympiad2['id']})
        assert created.status_code == 401
        updated = await anon.put(_rules_url(university, rule['id']), json={'subject': 'x'})
        assert updated.status_code == 401

    await register_user(client)
    created = await client.post(_rules_url(university), json={'olympiad_id': olympiad2['id']})
    assert created.status_code == 403
    updated = await client.put(_rules_url(university, rule['id']), json={'subject': 'x'})
    assert updated.status_code == 403
    verified = await client.post(
        _rules_url(university, rule['id']) + '/verification', json={'status': 'verified'}
    )
    assert verified.status_code == 403


async def test_rep_cannot_manage_foreign_university(client):
    university, olympiad, rep, rule = await _setup(client)
    other = await create_university(client, 'МФТИ')
    other_program = await _program(client, other['id'], 'Чужая программа')
    await login_user(client, rep['email'])

    foreign = await client.post(_rules_url(other), json={'olympiad_id': olympiad['id']})
    assert foreign.status_code == 403
    foreign_drafts = await client.get(_rules_url(other), params={'include_drafts': 'true'})
    assert foreign_drafts.status_code == 403

    # Чужая программа в своём правиле — отклоняется на сервере.
    mixed = await client.put(
        _rules_url(university, rule['id']), json={'program_ids': [other_program['id']]}
    )
    assert mixed.status_code == 400, mixed.text

    # Правило чужого вуза по «своему» URL не находится.
    other_rep = await university_rep_client(client, other['id'])
    stolen = await client.put(_rules_url(other, rule['id']), json={'subject': 'x'})
    assert stolen.status_code == 404
    assert other_rep['id'] != rep['id']


async def test_verification_requires_admin_and_rep_cannot_self_verify(client):
    university, _olympiad, rep, rule = await _setup(client)
    forbidden = await client.post(
        _rules_url(university, rule['id']) + '/verification', json={'status': 'verified'}
    )
    assert forbidden.status_code == 403

    # Через PUT представитель тоже не может проставить проверку.
    sneaky = await client.put(
        _rules_url(university, rule['id']), json={'verification_status': 'verified'}
    )
    assert sneaky.status_code in (200, 400, 422)
    detail = await client.get(_rules_url(university, rule['id']))
    assert detail.json()['verification_status'] == 'unverified'
    assert rep['id'] == detail.json()['createdBy']


async def test_rule_requires_published_olympiad_and_known_entities(client):
    university = await create_university(client, 'Университет ИТМО')
    archived = await create_olympiad(client, 'Старая олимпиада')
    gone = await client.post(f"/api/v1/admin/archive_olympiad/{archived['id']}")
    assert gone.status_code == 200, gone.text
    await university_rep_client(client, university['id'])

    on_archived = await client.post(_rules_url(university), json={'olympiad_id': archived['id']})
    assert on_archived.status_code == 409, on_archived.text

    unknown = await client.post(_rules_url(university), json={'olympiad_id': str(uuid.uuid4())})
    assert unknown.status_code == 404

    bad_type = await client.post(
        _rules_url(university), json={'olympiad_id': archived['id'], 'benefit_type': 'NONSENSE'}
    )
    assert bad_type.status_code == 422


# --- Дубликаты и конкурентность ------------------------------------------------


async def test_duplicate_rule_is_rejected(client):
    university, olympiad, _rep, rule = await _setup(client, subject='Математика')
    duplicate = await client.post(
        _rules_url(university),
        json={'olympiad_id': olympiad['id'], 'subject': 'математика'},
    )
    assert duplicate.status_code == 409, duplicate.text

    # Другой предмет — другое правило: у одной пары вуз-олимпиада их может быть несколько.
    second = await create_benefit_rule(
        client, university['id'], olympiad['id'], subject='Физика'
    )
    assert second['id'] != rule['id']
    page = await client.get(_rules_url(university))
    assert page.json()['total'] == 2


async def test_parallel_duplicate_creation_only_one_wins(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада «Физтех»')
    await university_rep_client(client, university['id'])

    async def attempt():
        return await client.post(_rules_url(university), json={'olympiad_id': olympiad['id']})

    results = await asyncio.gather(*(attempt() for _ in range(4)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 1, codes
    assert all(code in (201, 409) for code in codes), codes


# --- Версии и оптимистичная блокировка -----------------------------------------


async def test_every_change_is_a_version_and_rollback_is_new_unverified_version(client):
    university, olympiad, _rep, rule = await _setup(client, subject='Математика')
    assert rule['version'] == 1

    first = await client.put(
        _rules_url(university, rule['id']),
        json={'benefit_type': 'EGE_100', 'expected_version': 1, 'reason': 'приказ'},
    )
    assert first.status_code == 200, first.text
    assert first.json()['version'] == 2

    stale = await client.put(
        _rules_url(university, rule['id']), json={'subject': 'Физика', 'expected_version': 1}
    )
    assert stale.status_code == 409, stale.text

    history = await client.get(_rules_url(university, rule['id']) + '/versions')
    assert history.status_code == 200, history.text
    versions = history.json()['versions']
    assert [v['version'] for v in versions] == [1, 2]
    assert versions[1]['reason'] == 'приказ'
    assert versions[0]['snapshot']['benefit_type'] == 'BVI'

    # Администратор проверяет, затем откатываем — проверка не восстанавливается.
    await admin_client(client)
    doc = await client.post(
        _rules_url(university, rule['id']) + '/document',
        files={'file': ('order.pdf', PDF, 'application/pdf')},
    )
    assert doc.status_code == 200, doc.text
    await client.put(
        _rules_url(university, rule['id']), json={'source_url': 'https://itmo.ru/order'}
    )
    verified = await client.post(
        _rules_url(university, rule['id']) + '/verification', json={'status': 'verified'}
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()['verification_status'] == 'verified'

    rollback = await client.post(
        _rules_url(university, rule['id']) + '/rollback', json={'version': 1}
    )
    assert rollback.status_code == 200, rollback.text
    restored = rollback.json()
    assert restored['benefit_type'] == 'BVI'
    assert restored['verification_status'] == 'unverified'
    assert restored['status'] == 'published'

    history2 = await client.get(_rules_url(university, rule['id']) + '/versions')
    last = history2.json()['versions'][-1]
    assert last['is_rollback'] is True
    assert last['version'] == restored['version']
    assert history2.json()['current_version'] == restored['version']

    missing = await client.post(
        _rules_url(university, rule['id']) + '/rollback', json={'version': 99}
    )
    assert missing.status_code == 404


async def test_content_change_resets_verification_but_confirmation_is_separate(client):
    university, _olympiad, _rep, rule = await _setup(client, source_url='https://itmo.ru/x')
    confirmed = await client.post(
        _rules_url(university, rule['id']) + '/university-confirmation',
        json={'confirmed': True},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['university_confirmed'] is True
    assert confirmed.json()['verification_status'] == 'unverified'

    await admin_client(client)
    doc = await client.post(
        _rules_url(university, rule['id']) + '/document',
        files={'file': ('order.pdf', PDF, 'application/pdf')},
    )
    assert doc.status_code == 200, doc.text
    verified = await client.post(
        _rules_url(university, rule['id']) + '/verification', json={'status': 'verified'}
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()['verified_at'] is not None

    changed = await client.put(_rules_url(university, rule['id']), json={'subject': 'Физика'})
    assert changed.status_code == 200, changed.text
    assert changed.json()['verification_status'] == 'unverified'
    assert changed.json()['university_confirmed'] is True


# --- Политика проверки -------------------------------------------------------------


async def test_verified_requires_document_and_source_url(client):
    university, _olympiad, _rep, rule = await _setup(client)
    await admin_client(client)
    url = _rules_url(university, rule['id'])

    no_evidence = await client.post(url + '/verification', json={'status': 'verified'})
    assert no_evidence.status_code == 409, no_evidence.text

    doc = await client.post(
        url + '/document', files={'file': ('order.pdf', PDF, 'application/pdf')}
    )
    assert doc.status_code == 200, doc.text
    still_no_url = await client.post(url + '/verification', json={'status': 'verified'})
    assert still_no_url.status_code == 409

    await client.put(url, json={'source_url': 'https://itmo.ru/order'})
    ok = await client.post(url + '/verification', json={'status': 'verified'})
    assert ok.status_code == 200, ok.text

    bad = await client.post(url + '/verification', json={'status': 'nonsense'})
    assert bad.status_code == 422


async def test_rejected_rule_requires_note_and_disappears_from_public(client):
    university, olympiad, _rep, rule = await _setup(client)
    await admin_client(client)
    url = _rules_url(university, rule['id'])

    no_note = await client.post(url + '/verification', json={'status': 'rejected'})
    assert no_note.status_code in (400, 422), no_note.text

    rejected = await client.post(
        url + '/verification', json={'status': 'rejected', 'note': 'Документ не подтверждает'}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['verification_note'] == 'Документ не подтверждает'

    async with _anon() as anon:
        detail = await anon.get(f"/api/v1/benefit-rules/{rule['id']}")
        assert detail.status_code == 404
        page = await anon.get(f"/api/v1/universities/{university['id']}/olympiads")
        assert page.json()['total'] == 0
        back = await anon.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
        assert back.json()['total'] == 0

    # Представитель видит причину отклонения.
    await university_rep_client(client, university['id'])
    mine = await client.get(url)
    assert mine.status_code == 200
    assert mine.json()['verification_status'] == 'rejected'


# --- Жизненный цикл: публикация, архив, удаление --------------------------------


async def test_publish_unpublish_archive_and_delete_rules(client):
    university, olympiad, _rep, rule = await _setup(client, publish=False)
    url = _rules_url(university, rule['id'])

    published = await client.post(url + '/status', json={'status': 'published'})
    assert published.status_code == 200, published.text
    assert published.json()['published_at'] is not None

    cannot_delete = await client.delete(url)
    assert cannot_delete.status_code == 409

    back_to_draft = await client.post(url + '/status', json={'status': 'draft'})
    assert back_to_draft.status_code == 200, back_to_draft.text

    archived = await client.post(url + '/status', json={'status': 'archived'})
    assert archived.status_code == 200, archived.text
    async with _anon() as anon:
        assert (await anon.get(f"/api/v1/benefit-rules/{rule['id']}")).status_code == 404

    # После архива тот же набор условий можно завести заново.
    fresh = await create_benefit_rule(client, university['id'], olympiad['id'], publish=False)
    deleted = await client.delete(_rules_url(university, fresh['id']))
    assert deleted.status_code == 204, deleted.text
    gone = await client.get(_rules_url(university, fresh['id']))
    assert gone.status_code == 404

    invalid = await client.post(url + '/status', json={'status': 'nonsense'})
    assert invalid.status_code == 422


# --- Документ --------------------------------------------------------------------


async def test_rule_document_upload_validates_file_and_is_downloadable(client):
    university, _olympiad, _rep, rule = await _setup(client)
    url = _rules_url(university, rule['id'])

    bad_ext = await client.post(
        url + '/document', files={'file': ('evil.exe', b'MZ...', 'application/octet-stream')}
    )
    assert bad_ext.status_code == 400, bad_ext.text

    fake_pdf = await client.post(
        url + '/document', files={'file': ('fake.pdf', b'hello, not a pdf', 'application/pdf')}
    )
    assert fake_pdf.status_code == 400, fake_pdf.text

    traversal = await client.post(
        url + '/document', files={'file': ('../../etc/passwd.pdf', PDF, 'application/pdf')}
    )
    assert traversal.status_code == 200, traversal.text
    doc_info = traversal.json()['document']
    assert '/' not in doc_info['name'] and '..' not in doc_info['name']

    async with _anon() as anon:
        download = await anon.get(f"/api/v1/benefit-rules/{rule['id']}/document")
        assert download.status_code == 200
        assert download.content.startswith(b'%PDF')
        via_university = await anon.get(url + '/document')
        assert via_university.status_code == 200

    no_doc_rule = await create_benefit_rule(
        client, university['id'], _olympiad['id'], subject='Физика'
    )
    async with _anon() as anon:
        missing = await anon.get(f"/api/v1/benefit-rules/{no_doc_rule['id']}/document")
        assert missing.status_code == 404


# --- Программы -------------------------------------------------------------------


async def test_program_in_use_cannot_be_deleted(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада «Физтех»')
    program = await _program(client, university['id'])
    free = await _program(client, university['id'], 'Свободная программа')
    await university_rep_client(client, university['id'])
    await create_benefit_rule(
        client, university['id'], olympiad['id'], program_ids=[program['id']]
    )

    listed = await client.get(f"/api/v1/universities/{university['id']}/programs")
    counts = {p['id']: p['rules_count'] for p in listed.json()['programs']}
    assert counts[program['id']] == 1
    assert counts[free['id']] == 0

    blocked = await client.delete(
        f"/api/v1/universities/{university['id']}/programs/{program['id']}"
    )
    assert blocked.status_code == 409, blocked.text

    removed = await client.delete(
        f"/api/v1/universities/{university['id']}/programs/{free['id']}"
    )
    assert removed.status_code == 204, removed.text

    # Полная замена списка тоже не может «потерять» используемую программу.
    replaced = await client.put(
        f"/api/v1/universities/{university['id']}/programs",
        json={'programs': ['Совсем другая']},
    )
    assert replaced.status_code == 409, replaced.text


# --- Администратор: список, журнал, заявки на каталог -------------------------------


async def test_admin_benefit_rules_list_and_audit_log(client):
    university, _olympiad, _rep, rule = await _setup(client, publish=False)
    await admin_client(client)

    drafts = await client.get('/api/v1/admin/benefit-rules', params={'status': 'draft'})
    assert drafts.status_code == 200, drafts.text
    assert [r['id'] for r in drafts.json()['rules']] == [rule['id']]

    published = await client.get(
        '/api/v1/admin/benefit-rules', params={'status': 'published'}
    )
    assert published.json()['total'] == 0

    forbidden_for_plain = await register_user(client)
    assert forbidden_for_plain['id']
    denied = await client.get('/api/v1/admin/benefit-rules')
    assert denied.status_code == 403
    denied_audit = await client.get('/api/v1/admin/audit')
    assert denied_audit.status_code == 403

    await admin_client(client)
    await client.post(
        _rules_url(university, rule['id']) + '/verification',
        json={'status': 'rejected', 'note': 'нет документа'},
    )
    log = await client.get('/api/v1/admin/audit', params={'target_id': rule['id']})
    assert log.status_code == 200, log.text
    actions = [event['action'] for event in log.json()['events']]
    assert 'benefit_rule_create' in actions
    assert 'benefit_rule_verification' in actions
    assert log.json()['total'] == len(actions)

    only = await client.get(
        '/api/v1/admin/audit', params={'action': 'benefit_rule_verification', 'limit': 1}
    )
    assert only.json()['total'] >= 1
    assert len(only.json()['events']) == 1
    assert only.json()['events'][0]['details']['status'] == 'rejected'


async def test_catalog_request_flow(client):
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])

    empty = await client.post(
        f"/api/v1/universities/{university['id']}/catalog-requests",
        json={'kind': 'olympiad', 'text': '   '},
    )
    assert empty.status_code == 422

    created = await client.post(
        f"/api/v1/universities/{university['id']}/catalog-requests",
        json={'kind': 'olympiad', 'text': 'Добавьте олимпиаду «Новая»'},
    )
    assert created.status_code == 201, created.text
    request_id = created.json()['id']
    assert created.json()['status'] == 'open'

    mine = await client.get(f"/api/v1/universities/{university['id']}/catalog-requests")
    assert mine.status_code == 200, mine.text
    assert [r['id'] for r in mine.json()['requests']] == [request_id]

    await admin_client(client)
    queue = await client.get('/api/v1/admin/catalog-requests')
    assert queue.status_code == 200, queue.text
    assert queue.json()['total'] == 1

    resolved = await client.post(
        f'/api/v1/admin/catalog-requests/{request_id}/resolve',
        json={'status': 'resolved', 'note': 'Добавили'},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['status'] == 'resolved'
    assert resolved.json()['admin_note'] == 'Добавили'

    remaining = await client.get('/api/v1/admin/catalog-requests')
    assert remaining.json()['total'] == 0
    everything = await client.get('/api/v1/admin/catalog-requests', params={'status': 'all'})
    assert everything.json()['total'] == 1

    missing = await client.post(
        f'/api/v1/admin/catalog-requests/{uuid.uuid4()}/resolve', json={'status': 'rejected'}
    )
    assert missing.status_code == 404


async def test_legacy_bvi_endpoints_are_gone(client):
    university, olympiad, _rep, _rule = await _setup(client)
    legacy = await client.post(
        f"/api/v1/universities/{university['id']}/bvi", json={'olympiad_id': olympiad['id']}
    )
    assert legacy.status_code in (404, 405)
    admin_legacy = await client.get('/api/v1/admin/bvi')
    assert admin_legacy.status_code in (401, 403, 404, 405)
