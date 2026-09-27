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
# Документы-источники (PDF/XLSX/изображения) хранятся отдельно от временных
# файлов импорта; в тестах — тоже во временном каталоге.
os.environ['DOCS_DIR'] = os.environ.get('DOCS_DIR', '/tmp/papaya-docs-test')
# Импорт выполняется в процессе API: в тестовом окружении нет celery-воркера,
# иначе тесты ждали бы фоновую задачу из очереди.
os.environ['RSOSH_EXECUTION'] = 'inline'
# Меньшее разрешение рендеринга ускоряет OCR-тесты, качества хватает.
os.environ['RSOSH_PDF_DPI'] = os.environ.get('RSOSH_PDF_DPI', '200')
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
    os.makedirs(os.environ['DOCS_DIR'], exist_ok=True)
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


@pytest.fixture(autouse=True)
async def clean_state():
    """Изоляция тестов: каталоги, документы и пользователи пусты.

    Тесты работают с общей базой ``papaya_test``, поэтому перед каждым
    тестом доменные таблицы очищаются: иначе «Университет ИТМО» из одного
    теста мешал бы следующему. Заодно сбрасывается Redis (роли и профили
    читаются через версионный кэш) и каталог загруженных документов.
    """
    from sqlalchemy import text

    from app.database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                'TRUNCATE TABLE university_olympiads, universities, olympiads, '
                'docs, users CASCADE'
            )
        )
        await session.commit()

    _redis_client().flushdb()

    docs_dir = os.environ['DOCS_DIR']
    for name in os.listdir(docs_dir):
        path = os.path.join(docs_dir, name)
        if os.path.isfile(path):
            os.remove(path)
    yield


async def register_user(
    test_client: AsyncClient,
    email: str | None = None,
    password: str = 'StrongPass123!',
) -> dict:
    """Зарегистрировать пользователя; вернуть JSON из ответа.

    Внимание: у клиента одна cookie-сессия, поэтому регистрация переключает
    её на нового пользователя. Для сценариев с двумя ролями используйте
    ``login_user``, чтобы вернуть сессию администратору.
    """
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


async def login_user(
    test_client: AsyncClient,
    email: str,
    password: str = 'StrongPass123!',
) -> dict:
    """Войти под существующим аккаунтом (переключает сессию клиента)."""
    response = await test_client.post(
        '/api/v1/auth/login',
        json={'email': email, 'password': password},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def promote_role(user_id: str, role: str) -> None:
    """Сменить роль напрямую в БД и сбросить версионный кэш ролей.

    Только для ``USER`` и ``ADMIN``: инвариант «представитель = роль с вузом»
    защищён ещё и CHECK-ограничением в БД, поэтому создать ``EDITOR`` без
    университета таким путём нельзя. Для роли представителя есть
    ``university_rep_client``, для остальных ролей — ``set_user_role``
    (через API, где проверки видны в ответе).
    """
    from sqlalchemy import update

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    if role == 'EDITOR':
        raise ValueError(
            'promote_role не умеет назначать EDITOR: представитель обязан быть '
            'привязан к университету. Используйте university_rep_client '
            'или set_user_role.'
        )

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Users).where(Users.id == user_id).values(role=role)
        )
        await session.commit()
    # Роль читается через versioned-кэш Redis — после правки БД кэш сбрасываем.
    _redis_client().flushdb()


async def admin_client(test_client: AsyncClient) -> dict:
    """Клиент, авторизованный администратором Papaya.

    Регистрирует нового пользователя и повышает его до ADMIN: сессия
    клиента после вызова принадлежит администратору.
    """
    user = await register_user(test_client)
    await promote_role(user['id'], 'ADMIN')
    return user


async def create_university(
    test_client: AsyncClient,
    name: str = 'Университет ИТМО',
    **fields,
) -> dict:
    """Создать университет от имени администратора."""
    await admin_client(test_client)
    payload = {'name': name, **fields}
    response = await test_client.post('/api/v1/universities/add_university', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def create_olympiad(
    test_client: AsyncClient,
    name: str = 'Олимпиада школьников «Ломоносов»',
    **fields,
) -> dict:
    """Создать олимпиаду вручную от имени администратора."""
    await admin_client(test_client)
    payload = {'name': name, **fields}
    response = await test_client.post('/api/v1/olympiads/add_olympiad', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def university_rep_client(
    test_client: AsyncClient,
    university_id: str,
) -> dict:
    """Клиент представителя университета (роль EDITOR + привязка к вузу)."""
    from sqlalchemy import update

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    user = await register_user(test_client)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Users)
            .where(Users.id == user['id'])
            .values(role='EDITOR', university_id=university_id)
        )
        await session.commit()
    _redis_client().flushdb()
    return user


async def set_user_role(
    test_client: AsyncClient,
    user_id: str,
    role: str,
    university_id: str | None = None,
):
    """Назначить роль через публичный API администратора.

    Возвращает ответ целиком, чтобы тесты могли проверить коды ошибок
    (например, ``EDITOR`` без университета).
    """
    return await test_client.post(
        f'/api/v1/admin/role/{user_id}',
        json={'role': role, 'university_id': university_id},
    )


async def upload_document(
    test_client: AsyncClient,
    filename: str,
    payload: bytes,
    doc_type: str = 'RSOSH_LIST',
    name: str | None = None,
) -> dict:
    """Загрузить документ-источник (PDF/XLSX/изображение)."""
    response = await test_client.post(
        '/api/v1/docs/upload',
        files={'file': (filename, payload, 'application/octet-stream')},
        data={'type': doc_type, 'name': name or filename},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def run_import(test_client: AsyncClient, doc_id: str) -> dict:
    """Запустить импорт РСОШ и дождаться готовности (тесты идут inline)."""
    started = await test_client.post('/api/v1/imports/rsosh', json={'doc_id': doc_id})
    assert started.status_code == 202, started.text
    return started.json()


@pytest.fixture
def redis_flusher():
    """Синхронный сброс Redis из body-теста (для сценариев ручного управления)."""
    return _redis_client().flushdb