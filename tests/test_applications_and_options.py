"""Заявки, контакты и форма правила: контракт доверия и выбора.

Проверяется то, что видит пользователь по ту сторону формы:

* форма правила получает только непустые ветки «олимпиада → сезон → профиль»,
  иначе селект выглядит рабочим, но сохранить правило нельзя;
* аудит не теряет запись из-за ``datetime``/``UUID`` и не падает на
  нестандартном id сущности;
* заявка представителя всегда имеет почту для связи — явную или из аккаунта;
* фото заявки помечается метаданными, чтобы админ видел его отдельно;
* предложка университета повышает до представителя только при явном согласии;
* заявка на администратора одобряется только другим администратором и сразу
  выдаёт роль.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_profile,
    create_season,
    create_university,
    login_user,
    promote_role,
    register_user,
)

PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'fake-png-body'


async def test_benefit_form_options_returns_only_populated_tree(client):
    await admin_client(client)
    olympiad = await create_olympiad(client, 'Олимпиада с профилем')
    season = await create_season(client, olympiad['id'], label='2026/2027')
    profile = await create_profile(
        client, season['id'], name='Математика', rsosh_level='1'
    )
    # Сезон без профилей не должен попасть в форму: выбрать его нельзя.
    await create_season(client, olympiad['id'], label='2025/2026')

    empty = await create_olympiad(client, 'Олимпиада без профилей')
    await create_season(client, empty['id'], label='2026/2027')

    response = await client.get('/api/v1/benefit-rules/form-options')
    assert response.status_code == 200, response.text
    olympiads = response.json()['olympiads']
    ids = [item['id'] for item in olympiads]
    assert olympiad['id'] in ids
    assert empty['id'] not in ids

    branch = next(item for item in olympiads if item['id'] == olympiad['id'])
    assert [item['id'] for item in branch['seasons']] == [season['id']]
    assert [item['id'] for item in branch['seasons'][0]['profiles']] == [profile['id']]
    assert branch['seasons'][0]['profiles'][0]['rsosh_level'] == '1'


async def test_audit_sanitizes_values_and_survives_non_uuid_entity(client):
    from app.database import audit as audit_db

    marker = f'audit-{uuid.uuid4()}'
    entity_id = uuid.uuid4()
    await audit_db.log_action(
        marker,
        entity_id,
        'create',
        before={
            'when': datetime(2026, 11, 21, 10, 30, tzinfo=timezone.utc),
            'amount': Decimal('1.50'),
            'nested': {'id': entity_id},
        },
        after={'object': object()},
    )
    # Идентификатор-метка сезона не UUID: запись должна сохраниться,
    # потеряв только поле entity_id.
    await audit_db.log_action(marker, 'season-2026', 'update', after={'ok': True})

    logs = await audit_db.list_audit(entity_type=marker, limit=10)
    assert len(logs) == 2

    first = next(item for item in logs if item['action'] == 'create')
    assert first['before']['when'] == '2026-11-21T10:30:00+00:00'
    assert first['before']['amount'] == '1.50'
    assert first['before']['nested']['id'] == str(entity_id)
    assert isinstance(first['after']['object'], str)

    second = next(item for item in logs if item['action'] == 'update')
    assert second['entity_id'] is None
    assert second['after'] == {'ok': True}


async def test_representative_application_contact_email_falls_back_to_account(client):
    await admin_client(client)
    first = await create_university(client, 'Первый университет')
    second = await create_university(client, 'Второй университет')
    user = await register_user(client)

    fallback = await client.post(
        '/api/v1/representative-applications',
        json={'university_id': first['id']},
    )
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()['contact_email'] == user['email']

    explicit = await client.post(
        '/api/v1/representative-applications',
        json={
            'university_id': second['id'],
            'contact_email': 'rep-contact@example.com',
        },
    )
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()['contact_email'] == 'rep-contact@example.com'


async def test_representative_photo_is_marked_in_metadata(client):
    await admin_client(client)
    university = await create_university(client, 'Университет с фото')
    user = await register_user(client)
    application = await client.post(
        '/api/v1/representative-applications',
        json={'university_id': university['id'], 'justification': 'Работаю в вузе'},
    )
    assert application.status_code == 200, application.text
    app_id = application.json()['id']

    uploaded = await client.post(
        f'/api/v1/representative-applications/{app_id}/attachments',
        files={'file': ('photo.png', PNG_BYTES, 'image/png')},
        data={'name': 'Фото заявителя', 'kind': 'photo'},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()['metadata'] == {'kind': 'representative_photo'}

    listed = await client.get(
        f'/api/v1/representative-applications/{app_id}/attachments'
    )
    assert listed.status_code == 200, listed.text
    attachments = listed.json()['attachments']
    assert [item['name'] for item in attachments] == ['Фото заявителя']


async def test_university_proposal_promotes_only_with_consent(client):
    from app import database

    user = await register_user(client)
    without_consent = await client.post(
        '/api/v1/university-requests',
        json={'name': 'Университет без согласия', 'short_name': 'УБС'},
    )
    assert without_consent.status_code == 201, without_consent.text

    await admin_client(client)
    approved = await client.post(
        f"/api/v1/admin/entity-requests/{without_consent.json()['id']}/approve"
    )
    assert approved.status_code == 200, approved.text
    stored = await database.users.find_user_by_id(user['id'])
    assert stored['role'] == 'USER'
    assert stored['university_id'] is None

    await login_user(client, user['email'])
    with_consent = await client.post(
        '/api/v1/university-requests',
        json={
            'name': 'Университет с согласием',
            'become_representative': True,
            'contact_email': 'future-rep@example.com',
            'representative_justification': 'Я сотрудник приёмной комиссии',
        },
    )
    assert with_consent.status_code == 201, with_consent.text

    await admin_client(client)
    approved = await client.post(
        f"/api/v1/admin/entity-requests/{with_consent.json()['id']}/approve"
    )
    assert approved.status_code == 200, approved.text
    entity_id = approved.json()['entity_id']
    stored = await database.users.find_user_by_id(user['id'])
    assert stored['role'] == 'EDITOR'
    assert stored['university_id'] == entity_id


async def test_admin_application_cannot_be_self_approved_and_grants_admin(client):
    from app import database

    # 1. Своя заявка: пользователь становится админом другим путём, но
    #    одобрить собственную заявку всё равно нельзя.
    self_user = await register_user(client)
    own = await client.post(
        '/api/v1/admin-applications',
        json={
            'contact_email': self_user['email'],
            'motivation': 'Хочу проверять каталог',
        },
    )
    assert own.status_code == 201, own.text
    assert own.json()['status'] == 'pending'
    await promote_role(self_user['id'], 'ADMIN')

    self_approve = await client.post(
        f"/api/v1/admin/admin-applications/{own.json()['id']}/approve"
    )
    assert self_approve.status_code == 403, self_approve.text

    # 2. Чужая заявка: одобрение сразу выдаёт ADMIN.
    target = await register_user(client)
    application = await client.post(
        '/api/v1/admin-applications',
        json={
            'contact_email': 'candidate@example.com',
            'motivation': 'Веду олимпиадный кружок и знаю каталог',
        },
    )
    assert application.status_code == 201, application.text

    await admin_client(client)
    approved = await client.post(
        f"/api/v1/admin/admin-applications/{application.json()['id']}/approve"
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()['status'] == 'approved'

    stored = await database.users.find_user_by_id(target['id'])
    assert stored['role'] == 'ADMIN'


async def test_admin_application_reject_requires_reason(client):
    applicant = await register_user(client)
    application = await client.post(
        '/api/v1/admin-applications',
        json={
            'contact_email': applicant['email'],
            'motivation': 'Хочу помогать проекту',
        },
    )
    assert application.status_code == 201, application.text

    await admin_client(client)
    rejected = await client.post(
        f"/api/v1/admin/admin-applications/{application.json()['id']}/reject",
        json={'reason': 'Недостаточно опыта модерации'},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['status'] == 'rejected'
    assert rejected.json()['rejection_reason'] == 'Недостаточно опыта модерации'
