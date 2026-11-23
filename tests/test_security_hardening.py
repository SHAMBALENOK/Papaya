"""Регрессии безопасности: заголовки, конфигурация, Docker и роли.

Каждый тест закрывает подтверждённую проблему, а не гипотетическую:

* ответы API и SPA несут защитные заголовки (кликджекинг, MIME-sniffing);
* пустой ``COOKIE_SECURE`` не отключает production-дефолт ``Secure``;
* приложение не стартует с общеизвестным секретом JWT;
* PostgreSQL, Redis и pgAdmin не публикуются во внешнюю сеть;
* заявку представителя нельзя одобрить самому себе и нельзя понизить
  администратора до представителя через эту заявку.
"""

from pathlib import Path

import pytest

from tests.conftest import (
    admin_client,
    login_user,
    promote_role,
    register_user,
)

ROOT = Path(__file__).resolve().parents[1]


async def test_security_headers_are_set_on_api_and_spa(client):
    api = await client.get('/api/v1/health')
    assert api.status_code == 200
    assert api.headers['x-content-type-options'] == 'nosniff'
    assert api.headers['x-frame-options'] == 'DENY'
    assert api.headers['referrer-policy'] == 'strict-origin-when-cross-origin'
    assert 'geolocation=()' in api.headers['permissions-policy']
    assert "frame-ancestors 'none'" in api.headers['content-security-policy']
    # Тестовое окружение работает по HTTP: HSTS выставляется только в production.
    assert 'strict-transport-security' not in api.headers

    spa = await client.get('/')
    assert spa.status_code == 200
    assert spa.headers['x-content-type-options'] == 'nosniff'
    assert spa.headers['x-frame-options'] == 'DENY'


def test_empty_cookie_secure_uses_environment_default(monkeypatch):
    from app.core import config

    monkeypatch.setenv('PAPAYA_TEST_BOOL', '')
    assert config._env_bool('PAPAYA_TEST_BOOL', True) is True
    assert config._env_bool('PAPAYA_TEST_BOOL', False) is False

    monkeypatch.setenv('PAPAYA_TEST_BOOL', 'false')
    assert config._env_bool('PAPAYA_TEST_BOOL', True) is False


def test_placeholder_jwt_is_rejected_outside_tests(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config, 'DATABASE_URL', 'postgresql+asyncpg://u:p@db/x')
    monkeypatch.setattr(config, 'JWT_KEY', 'change_this_secret_key')

    monkeypatch.setattr(config, 'ENVIRONMENT', 'development')
    with pytest.raises(RuntimeError, match='JWT_KEY'):
        config.validate_config()

    # Тестовое окружение — осознанное исключение, иначе тесты не стартовали бы.
    monkeypatch.setattr(config, 'ENVIRONMENT', 'testing')
    config.validate_config()


def test_infrastructure_ports_are_bound_to_loopback():
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
    assert '"127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"' in compose
    assert '"127.0.0.1:${REDIS_HOST_PORT:-6379}:6379"' in compose
    assert '"127.0.0.1:${PGADMIN_HOST_PORT:-5050}:80"' in compose
    assert '"5432:5432"' not in compose
    assert '"6379:6379"' not in compose
    assert '"5050:80"' not in compose


async def test_admin_cannot_self_approve_representative_application(client):
    await admin_client(client)
    university = await client.post(
        '/api/v1/universities/add_university',
        json={'name': 'Университет самопроверки'},
    )
    assert university.status_code == 201, university.text

    application = await client.post(
        '/api/v1/representative-applications',
        json={
            'university_id': university.json()['id'],
            'justification': 'Проверяю собственную заявку',
        },
    )
    assert application.status_code == 200, application.text

    reviewed = await client.post(
        f"/api/v1/admin/representative-applications/"
        f"{application.json()['id']}/review",
        json={'status': 'approved'},
    )
    assert reviewed.status_code == 403, reviewed.text

    from app import database

    stored = await database.representative.get_application(application.json()['id'])
    assert stored['status'] == 'pending'


async def test_admin_is_not_demoted_by_representative_application(client):
    await admin_client(client)
    university = await client.post(
        '/api/v1/universities/add_university',
        json={'name': 'Университет понижения'},
    )
    assert university.status_code == 201, university.text

    applicant = await register_user(client)
    application = await client.post(
        '/api/v1/representative-applications',
        json={
            'university_id': university.json()['id'],
            'justification': 'Заявка администратора',
        },
    )
    assert application.status_code == 200, application.text

    # Заявитель успел стать администратором до рассмотрения заявки.
    await promote_role(applicant['id'], 'ADMIN')
    reviewer = await register_user(client)
    await promote_role(reviewer['id'], 'ADMIN')
    await login_user(client, reviewer['email'])

    reviewed = await client.post(
        f"/api/v1/admin/representative-applications/"
        f"{application.json()['id']}/review",
        json={'status': 'approved'},
    )
    assert reviewed.status_code == 409, reviewed.text

    from app import database

    stored_user = await database.users.find_user_by_id(applicant['id'])
    assert stored_user['role'] == 'ADMIN'
    stored_app = await database.representative.get_application(
        application.json()['id']
    )
    assert stored_app['status'] == 'pending'


async def test_regular_representative_approval_still_grants_editor(client):
    await admin_client(client)
    university = await client.post(
        '/api/v1/universities/add_university',
        json={'name': 'Университет обычной заявки'},
    )
    assert university.status_code == 201, university.text

    applicant = await register_user(client)
    application = await client.post(
        '/api/v1/representative-applications',
        json={
            'university_id': university.json()['id'],
            'justification': 'Я сотрудник приёмной комиссии',
        },
    )
    assert application.status_code == 200, application.text

    await admin_client(client)
    reviewed = await client.post(
        f"/api/v1/admin/representative-applications/"
        f"{application.json()['id']}/review",
        json={'status': 'approved'},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['status'] == 'approved'

    from app import database

    stored_user = await database.users.find_user_by_id(applicant['id'])
    assert stored_user['role'] == 'EDITOR'
    assert stored_user['university_id'] == university.json()['id']
