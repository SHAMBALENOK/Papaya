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


async def _db_state() -> tuple[bool, bool]:
    """Вернуть (управляется_ли_база_alembic, есть_ли_таблицы_моделей)."""
    import asyncpg

    url = os.environ['DATABASE_URL']
    dsn = url.replace(SCHEME, 'postgresql://', 1)
    conn = await asyncpg.connect(dsn)
    try:
        has_version = await _table_exists(conn, 'alembic_version')
        has_users = await _table_exists(conn, 'users')
        has_events = await _table_exists(conn, 'events')
        return has_version, has_users or has_events
    finally:
        await conn.close()


def main() -> int:
    """Определить состояние БД и применить нужную стратегию миграции."""
    if not os.environ.get('DATABASE_URL'):
        print('WARN: DATABASE_URL is not set, skipping migrations', file=sys.stderr)
        return 0

    has_version, has_schema = asyncio.run(_db_state())
    if has_version:
        print('INFO: database is under Alembic control -> upgrade head')
        _alembic('upgrade', 'head')
    elif has_schema:
        # Старые базы: не пересоздаём таблицы, а закрепляем baseline-ревизию и
        # применяем только последующие миграции (индексы и т.д.).
        print('INFO: legacy schema detected -> stamp %s then upgrade head' % BASELINE_REVISION)
        _alembic('stamp', BASELINE_REVISION)
        _alembic('upgrade', 'head')
    else:
        print('INFO: empty database -> upgrade head')
        _alembic('upgrade', 'head')
    return 0


if __name__ == '__main__':
    sys.exit(main())