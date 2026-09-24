"""REST API доменных сущностей: Organizations / Olympiads / Docs.

Проверяются ролевые ограничения (USER vs ADMIN vs ORGANIZATION_ADMIN),
object-level доступ организации и жизненный цикл файлов документов.
"""

import uuid

from tests.conftest import promote_role, register_user

FAKE_PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n'


async def _bind_org_admin(client, user_id: str, org_id: str) -> None:
    """Назначить ORGANIZATION_ADMIN и привязать организацию (прямое изменение БД)."""
    from sqlalchemy import update

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Users)
            .where(Users.id == uuid.UUID(user_id))
            .values(role='ORGANIZATION_ADMIN', organization_id=uuid.UUID(org_id))
        )
        await session.commit()
    from tests.conftest import _redis_client

    _redis_client().flushdb()


# ---------------------------------------------------------------- Organisations


async def test_user_cannot_create_organization(client):
    await register_user(client)
    response = await client.post(
        '/api/v1/organizations',
        json={
            'name': 'Университет',
            'type': 'UNIVERSITY',
            'short_name': 'УН',
        },
    )
    assert response.status_code == 403


async def test_admin_creates_and_reads_organization(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    created = await client.post(
        '/api/v1/organizations',
        json={
            'name': 'Московский государственный университет',
            'short_name': 'МГУ',
            'type': 'UNIVERSITY',
            'website': 'https://msu.ru',
        },
    )
    assert created.status_code == 201, created.text
    org = created.json()
    assert org['type'] == 'UNIVERSITY'
    assert org['name'] == 'Московский государственный университет'

    got = await client.get(f"/api/v1/organizations/{org['id']}")
    assert got.status_code == 200
    assert got.json()['short_name'] == 'МГУ'

    listed = await client.get('/api/v1/organizations')
    assert any(item['name'] == 'МГУ' or item['short_name'] == 'МГУ'
               for item in listed.json())


async def test_invalid_organization_type_rejected(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    response = await client.post(
        '/api/v1/organizations',
        json={'name': 'Плохой тип', 'type': 'GOVERNMENT'},
    )
    assert response.status_code == 422


async def test_org_admin_updates_only_own_organization(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Моя организация', 'type': 'ORGANIZER'},
        )
    ).json()

    foreign = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Чужая организация', 'type': 'ORGANIZER'},
        )
    ).json()

    org_admin = await register_user(client)
    await _bind_org_admin(client, org_admin['id'], org['id'])

    own_update = await client.patch(
        f"/api/v1/organizations/{org['id']}",
        json={'description': 'Обновлено представителем'},
    )
    assert own_update.status_code == 200
    assert own_update.json()['description'] == 'Обновлено представителем'

    foreign_update = await client.patch(
        f"/api/v1/organizations/{foreign['id']}",
        json={'description': 'Взлом'},
    )
    assert foreign_update.status_code == 403

    foreign_delete = await client.delete(
        f"/api/v1/organizations/{foreign['id']}"
    )
    assert foreign_delete.status_code == 403


async def test_admin_deletes_organization_after_admin_creates(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Кандидат на удаление', 'type': 'OTHER'},
        )
    ).json()

    deleted = await client.delete(f"/api/v1/organizations/{org['id']}")
    assert deleted.status_code == 200

    gone = await client.get(f"/api/v1/organizations/{org['id']}")
    assert gone.status_code == 404


# ------------------------------------------------------------------ Olympiads


async def test_admin_creates_and_reads_olympiad(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Организатор олимпиады', 'type': 'ORGANIZER'},
        )
    ).json()

    created = await client.post(
        '/api/v1/olympiads',
        json={
            'name': 'Всероссийская олимпиада школьников',
            'organizer_ids': [org['id']],
            'subjects': ['математика', 'физика'],
            'levels': ['1', '2'],
            'years': ['2025', '2026'],
        },
    )
    assert created.status_code == 201, created.text
    olympiad = created.json()
    assert olympiad['organizer_ids'] == [org['id']]
    assert olympiad['status'] == 'PUBLISHED'

    got = await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    assert got.status_code == 200
    assert got.json()['name'] == 'Всероссийская олимпиада школьников'

    listed = await client.get(
        '/api/v1/olympiads', params={'status': 'PUBLISHED'}
    )
    names = [item['name'] for item in listed.json()]
    assert 'Всероссийская олимпиада школьников' in names


async def test_user_cannot_create_olympiad(client):
    await register_user(client)
    response = await client.post(
        '/api/v1/olympiads',
        json={'name': 'Нельзя создать'},
    )
    assert response.status_code == 403


async def test_admin_updates_olympiad_status(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    olympiad = (
        await client.post(
            '/api/v1/olympiads',
            json={'name': 'Архивируемая'},
        )
    ).json()

    archived = await client.patch(
        f"/api/v1/olympiads/{olympiad['id']}",
        json={'status': 'ARCHIVED', 'description': 'Закрыто'},
    )
    assert archived.status_code == 200
    assert archived.json()['status'] == 'ARCHIVED'


async def test_admin_deletes_olympiad(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    olympiad = (
        await client.post(
            '/api/v1/olympiads',
            json={'name': 'Кандидат на удаление'},
        )
    ).json()

    deleted = await client.delete(f"/api/v1/olympiads/{olympiad['id']}")
    assert deleted.status_code == 200
    assert (
        await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    ).status_code == 404


async def test_unknown_olympiad_returns_404(client):
    await register_user(client)
    response = await client.get(f'/api/v1/olympiads/{uuid.uuid4()}')
    assert response.status_code == 404


async def test_org_admin_creates_olympiad_only_for_own_org(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    own_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Своя организация', 'type': 'ORGANIZER'},
        )
    ).json()
    foreign_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Чужая организация', 'type': 'ORGANIZER'},
        )
    ).json()

    org_admin = await register_user(client)
    await _bind_org_admin(client, org_admin['id'], own_org['id'])

    created = await client.post(
        '/api/v1/olympiads',
        json={
            'name': 'Олимпиада представителя',
            'organizer_ids': [foreign_org['id']],
        },
    )
    assert created.status_code == 201, created.text
    olympiad = created.json()
    assert olympiad['organizer_ids'] == [own_org['id']]


async def test_org_admin_manages_only_own_olympiad(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    own_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Своя организация', 'type': 'ORGANIZER'},
        )
    ).json()
    foreign_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Чужая организация', 'type': 'ORGANIZER'},
        )
    ).json()

    own_olympiad = (
        await client.post(
            '/api/v1/olympiads',
            json={
                'name': 'Своя олимпиада',
                'organizer_ids': [own_org['id']],
            },
        )
    ).json()
    foreign_olympiad = (
        await client.post(
            '/api/v1/olympiads',
            json={
                'name': 'Чужая олимпиада',
                'organizer_ids': [foreign_org['id']],
            },
        )
    ).json()

    org_admin = await register_user(client)
    await _bind_org_admin(client, org_admin['id'], own_org['id'])

    own_update = await client.patch(
        f"/api/v1/olympiads/{own_olympiad['id']}",
        json={'description': 'Обновлено представителем'},
    )
    assert own_update.status_code == 200
    assert own_update.json()['description'] == 'Обновлено представителем'

    foreign_update = await client.patch(
        f"/api/v1/olympiads/{foreign_olympiad['id']}",
        json={'description': 'Взлом'},
    )
    assert foreign_update.status_code == 403

    foreign_delete = await client.delete(
        f"/api/v1/olympiads/{foreign_olympiad['id']}"
    )
    assert foreign_delete.status_code == 403

    own_delete = await client.delete(f"/api/v1/olympiads/{own_olympiad['id']}")
    assert own_delete.status_code == 200
    assert (
        await client.get(f"/api/v1/olympiads/{own_olympiad['id']}")
    ).status_code == 404


async def test_org_admin_sees_only_own_org_in_listing(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    own_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Своя организация', 'type': 'ORGANIZER'},
        )
    ).json()
    await client.post(
        '/api/v1/organizations',
        json={'name': 'Чужая организация', 'type': 'ORGANIZER'},
    )

    org_admin = await register_user(client)
    await _bind_org_admin(client, org_admin['id'], own_org['id'])

    listed = await client.get('/api/v1/organizations')
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]['id'] == own_org['id']


# ---------------------------------------------------------------------- Docs


async def test_admin_uploads_and_downloads_document(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    uploaded = await client.post(
        '/api/v1/docs',
        params={'type': 'RSOSH_LIST'},
        files={
            'file': (
                'rsosh_2026.pdf',
                FAKE_PDF,
                'application/pdf',
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    doc = uploaded.json()
    assert doc['type'] == 'RSOSH_LIST'
    assert doc['status'] == 'UPLOADED'
    assert doc['storage_key']
    assert len(doc['checksum']) == 64

    got = await client.get(f"/api/v1/docs/{doc['id']}")
    assert got.status_code == 200
    assert got.json()['checksum'] == doc['checksum']

    download = await client.get(f"/api/v1/docs/{doc['id']}/file")
    assert download.status_code == 200
    assert download.headers['content-type'] == 'application/pdf'
    assert download.content == FAKE_PDF


async def test_doc_listing(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    uploaded = await client.post(
        '/api/v1/docs',
        params={'type': 'UNIVERSITY_DOCUMENT'},
        files={'file': ('rule.pdf', FAKE_PDF, 'application/pdf')},
    )
    assert uploaded.status_code == 201
    listed = await client.get('/api/v1/docs')
    assert listed.status_code == 200
    docs = listed.json()
    assert any(
        doc['name'] == 'rule.pdf'
        and doc['type'] == 'UNIVERSITY_DOCUMENT'
        for doc in docs
    )


async def test_upload_rejects_bad_extension(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    response = await client.post(
        '/api/v1/docs',
        files={'file': ('evil.exe', b'MZ', 'application/octet-stream')},
    )
    assert response.status_code == 400


async def test_user_cannot_upload_document(client):
    await register_user(client)
    response = await client.post(
        '/api/v1/docs',
        files={'file': ('doc.pdf', FAKE_PDF, 'application/pdf')},
    )
    assert response.status_code == 403


async def test_docs_object_level_access(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')

    own_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Своя организация', 'type': 'ORGANIZER'},
        )
    ).json()
    foreign_org = (
        await client.post(
            '/api/v1/organizations',
            json={'name': 'Чужая организация', 'type': 'ORGANIZER'},
        )
    ).json()

    own_doc = (
        await client.post(
            '/api/v1/docs',
            params={'type': 'OLYMPIAD_REGULATION', 'organization_id': own_org['id']},
            files={'file': ('own.pdf', FAKE_PDF, 'application/pdf')},
        )
    ).json()
    foreign_doc = (
        await client.post(
            '/api/v1/docs',
            params={'type': 'OLYMPIAD_REGULATION', 'organization_id': foreign_org['id']},
            files={'file': ('foreign.pdf', FAKE_PDF, 'application/pdf')},
        )
    ).json()

    org_admin = await register_user(client)
    await _bind_org_admin(client, org_admin['id'], own_org['id'])

    own_download = await client.get(f"/api/v1/docs/{own_doc['id']}/file")
    assert own_download.status_code == 200

    foreign_download = await client.get(f"/api/v1/docs/{foreign_doc['id']}/file")
    assert foreign_download.status_code == 403

    foreign_meta = await client.get(f"/api/v1/docs/{foreign_doc['id']}")
    assert foreign_meta.status_code == 403

    listed = await client.get('/api/v1/docs')
    body = listed.json()
    assert len(body) == 1
    assert body[0]['id'] == own_doc['id']


async def test_admin_deletes_document(client):
    admin = await register_user(client)
    await promote_role(admin['id'], 'ADMIN')
    doc = (
        await client.post(
            '/api/v1/docs',
            files={'file': ('delete_me.pdf', FAKE_PDF, 'application/pdf')},
        )
    ).json()

    deleted = await client.delete(f"/api/v1/docs/{doc['id']}")
    assert deleted.status_code == 200
    assert (
        await client.get(f"/api/v1/docs/{doc['id']}")
    ).status_code == 404