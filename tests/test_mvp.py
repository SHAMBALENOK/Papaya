import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    university_rep_client,
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

    # combined filters
    filt = await client.get(
        '/api/v1/benefits',
        params={'university_id': university['id'], 'benefit_type': 'BVI', 'subject': 'Физика', 'program_id': program['id']},
    )
    assert filt.status_code == 200
    assert len(filt.json()['rules']) == 1

    # version history
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