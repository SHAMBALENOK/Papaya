"""Общее окружение API-тестов Papaya.

Запуск внутри Docker-сети проекта:

    docker compose --profile testing run --rm test

Тесты работают с отдельной базой ``papaya_test`` (миграции выполняются здесь
же, рабочая БД проекта не затрагивается) и «общим» Redis, который чистится
перед сессией. Окружение настраивается через переменные окружения ДО импорта
``app.main``, потому что конфигурация приложения читается при импорте.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_DB_NAME = 'papaya_test'
TEST_DB_URL = os.environ.get(
    'DATABASE_URL_TEST',
    f'postgresql+asyncpg://postgres:postgres@postgres:5432/{TEST_DB_NAME}',
)
ADMIN_DB_URL = TEST_DB_URL.replace('+asyncpg', '').replace(
    f'/{TEST_DB_NAME}', '/postgres'
)

os.environ['DATABASE_URL'] = TEST_DB_URL
os.environ['JWT_KEY'] = os.environ.get(
    'JWT_KEY', 'pytest_secret_key_for_local_tests_only'
)
os.environ['ENVIRONMENT'] = os.environ.get('ENVIRONMENT', 'testing')
os.environ['REDIS_HOST'] = os.environ.get('REDIS_HOST', 'redis')
os.environ['REDIS_PORT'] = os.environ.get('REDIS_PORT', '6379')
os.environ['REDIS_URL'] = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
os.environ['CACHE_TTL'] = os.environ.get('CACHE_TTL', '60')
os.environ['MAX_UPLOAD_MB'] = os.environ.get('MAX_UPLOAD_MB', '1')
os.environ['TABLES_DIR'] = os.environ.get('TABLES_DIR', '/tmp/papaya-tables-test')
os.environ['COOKIE_SECURE'] = 'false'

import pytest  # noqa: E402
import redis as redis_sync  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


def _redis_client() -> redis_sync.Redis:
    return redis_sync.Redis(
        host=os.environ['REDIS_HOST'],
        port=int(os.environ['REDIS_PORT']),
    )


def _prepare_database() -> None:
    """Пересоздать тестовую БД и накатить миграции в отдельном процессе.

    pytest-asyncio (режим auto) исполняет даже синхронные генератор-фикстуры
    внутри уже запущенного event loop, а alembic env.py и инлайн-скрипты зовут
    ``asyncio.run()`` — это конфликт. Поэтому вся подготовка уходит в
    subprocess (отдельный интерпретатор и loop), как это делает и сам проект
    (setup.sh -> ensure_db_schema.py).
    """
    create_script = (
        'import asyncio, asyncpg\n'
        'async def main():\n'
        f'    conn = await asyncpg.connect({ADMIN_DB_URL!r})\n'
        f'    await conn.execute("DROP DATABASE IF EXISTS {TEST_DB_NAME}")\n'
        f'    await conn.execute("CREATE DATABASE {TEST_DB_NAME}")\n'
        '    await conn.close()\n'
        'asyncio.run(main())\n'
    )
    subprocess.run(
        [sys.executable, '-c', create_script],
        check=True,
        capture_output=True,
    )
    migration_env = dict(os.environ, DATABASE_URL=TEST_DB_URL)
    subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=str(ROOT),
        env=migration_env,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope='session', autouse=True)
def prepare_environment():
    """Свежая схема papaya_test (drop/create + миграции) и чистый Redis."""
    _prepare_database()

    os.makedirs(os.environ['TABLES_DIR'], exist_ok=True)
    _redis_client().flushdb()
    yield


@pytest.fixture
async def client():
    """httpx-клиент без внешнего HTTP: живой FastAPI поверх ASGI.

    ``LifespanManager`` обязательно запускает startup/shutdown приложения:
    только так создаются пулы соединений (``redis_pool``, БД), которые
    переиспользуются API-зависимостями через ``request.app.state``.
    """
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url='http://testserver',
        ) as test_client:
            yield test_client


async def register_user(
    test_client: AsyncClient,
    email: str | None = None,
    password: str = 'StrongPass123!',
) -> dict:
    """Зарегистрировать пользователя; вернуть JSON из ответа."""
    suffix = datetime.now(timezone.utc).strftime('%f')
    email = email or f'test_{suffix}@example.com'
    response = await test_client.post(
        '/api/v1/auth/register',
        json={
            'name': 'Test',
            'surname': 'User',
            'email': email,
            'password': password,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def promote_role(user_id: str, role: str) -> None:
    """Сменить роль напрямую в БД и сбросить версионный кэш ролей."""
    from sqlalchemy import update

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Users).where(Users.id == user_id).values(role=role)
        )
        await session.commit()
    # Роль читается через versioned-кэш Redis — после правки БД кэш сбрасываем.
    _redis_client().flushdb()


@pytest.fixture
def redis_flusher():
    """Синхронный сброс Redis из body-теста (для сценариев ручного управления)."""
    return _redis_client().flushdb