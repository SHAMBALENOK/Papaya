"""Применить миграции Alembic перед стартом приложения.

Скрипт учитывает три состояния базы данных:

1. База уже управляется Alembic (есть таблица ``alembic_version``) —
   выполняется обычный ``alembic upgrade head``.
2. Чистая база (нет ни одной таблицы) — ``alembic upgrade head`` создаёт схему
   с нуля (работает и для тестовых баз).
3. Существующая база, созданная старым кодом через
   ``Base.metadata.create_all`` (таблицы есть, а ``alembic_version`` нет) —
   сначала выполняется ``alembic stamp 0001`` (без применения DDL, чтобы не
   наткнуться на уже существующие таблицы), затем ``alembic upgrade head`` —
   таким образом применяются только инкрементальные миграции, например 0002
   с индексами.

Запуск: python scripts/ensure_db_schema.py (нужна переменная DATABASE_URL).
"""

import asyncio
import os
import subprocess
import sys

# Схема, использующаяся в .env / docker-compose (asyncpg-драйвер)
SCHEME = 'postgresql+asyncpg://'
# Название ревизии, соответствующее уже существующей схеме create_all
BASELINE_REVISION = '0001'
# Ключ advisory-блокировки PostgreSQL, сериализующий миграции между
# процессами (web и celery стартуют параллельно и оба зовут этот скрипт).
MIGRATION_LOCK_KEY = 0x50415041  # 'PAPA'


async def _table_exists(conn, table: str) -> bool:
    """Проверить наличие таблицы в схеме public."""
    return bool(
        await conn.fetchval(
            'SELECT EXISTS (SELECT 1 FROM information_schema.tables '
            'WHERE table_schema = $1 AND table_name = $2)',
            'public',
            table,
        )
    )


def _alembic(*args) -> None:
    """Запустить alembic как модуль и упасть при ошибке."""
    subprocess.run(
        [sys.executable, '-m', 'alembic', *args],
        check=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


async def _read_state(conn) -> tuple[bool, bool]:
    """Вернуть (управляется_ли_база_alembic, есть_ли_таблицы_моделей).

    Читается по уже открытому соединению: вызывающий обязан держать
    advisory-блокировку, чтобы снимок не устарел между чтением и решением о
    ``stamp``/``upgrade``.
    """
    has_version = await _table_exists(conn, 'alembic_version')
    has_users = await _table_exists(conn, 'users')
    has_olympiads = await _table_exists(conn, 'olympiads')
    return has_version, has_users or has_olympiads


async def _ensure_database(dsn: str) -> None:
    """Создать целевую базу, если её ещё нет.

    Alembic умеет создавать схему в пустой базе, но не саму базу: без этого
    шага запуск на чистой машине (и на удалённой тестовой БД) падал бы с
    «database does not exist» ещё до первой миграции.

    Проверка «есть ли база» и ``CREATE DATABASE`` неатомарны: web и celery
    стартуют параллельно, и второй процесс может создать ту же базу между
    проверкой первого и его ``CREATE``. Это нормальная гонка — целевая база
    уже существует, и повторное создание не нужно.
    """
    import asyncpg

    database = dsn.rsplit('/', 1)[-1].split('?')[0]
    if not database or not database.replace('_', '').isalnum():
        print('WARN: cannot parse database name from DATABASE_URL', file=sys.stderr)
        return

    admin_dsn = dsn.rsplit('/', 1)[0] + '/postgres'
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            'SELECT 1 FROM pg_database WHERE datname = $1', database
        )
        if not exists:
            print(f'INFO: creating database {database}')
            try:
                await conn.execute(f'CREATE DATABASE "{database}"')
            except asyncpg.exceptions.DuplicateDatabaseError:
                print(
                    f'INFO: database {database} was created by another process',
                    file=sys.stderr,
                )
    finally:
        await conn.close()


def _dsn() -> str:
    """DATABASE_URL в форме, понятной asyncpg (без ``+asyncpg``)."""
    return os.environ['DATABASE_URL'].replace(SCHEME, 'postgresql://', 1)


async def _run_migrations_locked() -> None:
    """Создать базу при необходимости и применить миграции под блокировкой.

    Web и celery стартуют одновременно и оба выполняют этот скрипт. Без
    блокировки два ``alembic upgrade head`` могли бы пойти параллельно и,
    например, оба попытаться создать один индекс. ``pg_advisory_lock``
    сериализует их: второй процесс ждёт первый на той же паре (база, ключ).
    Блокировка снимается автоматически при разрыве соединения, но мы снимаем
    её явно.

    Состояние схемы читается **после** захвата блокировки. Снимок до неё
    успевает устареть: пока второй процесс ждал, первый уже закрепил baseline
    и довёл базу до head. По устаревшему снимку второй процесс снова увидел бы
    «старую схему без ``alembic_version``» и повторно закрепил baseline
    (``stamp 0001``), а затем заново прогнал ``upgrade head``.
    """
    import asyncpg

    await _ensure_database(_dsn())
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute('SELECT pg_advisory_lock($1)', MIGRATION_LOCK_KEY)
        has_version, has_schema = await _read_state(conn)
        if has_version:
            print('INFO: database is under Alembic control -> upgrade head')
            _alembic('upgrade', 'head')
        elif has_schema:
            # Старые базы: не пересоздаём таблицы, а закрепляем baseline-ревизию
            # и применяем только последующие миграции (индексы и т.д.).
            print('INFO: legacy schema detected -> stamp %s then upgrade head' % BASELINE_REVISION)
            _alembic('stamp', BASELINE_REVISION)
            _alembic('upgrade', 'head')
        else:
            print('INFO: empty database -> upgrade head')
            _alembic('upgrade', 'head')
    finally:
        await conn.execute('SELECT pg_advisory_unlock($1)', MIGRATION_LOCK_KEY)
        await conn.close()


def main() -> int:
    """Определить состояние БД и применить нужную стратегию миграции."""
    if not os.environ.get('DATABASE_URL'):
        print('WARN: DATABASE_URL is not set, skipping migrations', file=sys.stderr)
        return 0

    asyncio.run(_run_migrations_locked())
    return 0


if __name__ == '__main__':
    sys.exit(main())