"""Регрессии стартового скрипта миграций (``scripts/ensure_db_schema.py``).

Web и celery запускают скрипт одновременно, поэтому важны две вещи:

- состояние схемы читается **после** захвата advisory-блокировки, иначе
  решение ``stamp``/``upgrade`` принимается по устаревшему снимку;
- гонка при создании базы не роняет процесс: ``CREATE DATABASE`` может
  проиграть параллельному процессу, и это нормальный исход.
"""

import asyncpg

import scripts.ensure_db_schema as schema


class _FakeConn:
    """Подмена asyncpg-соединения: запоминает запросы и умеет упасть на CREATE."""

    def __init__(self, *, exists: bool = True, create_error: Exception | None = None):
        self.exists = exists
        self.create_error = create_error
        self.queries: list[str] = []

    async def fetchval(self, query, *args):
        self.queries.append(query)
        if 'pg_database' in query:
            return 1 if self.exists else None
        return None

    async def execute(self, query, *args):
        self.queries.append(query)
        if 'CREATE DATABASE' in query and self.create_error is not None:
            raise self.create_error

    async def close(self):
        pass


async def test_ensure_database_skips_existing(monkeypatch):
    """Существующая база повторно не создаётся."""
    conn = _FakeConn(exists=True)

    async def fake_connect(dsn):
        return conn

    monkeypatch.setattr(asyncpg, 'connect', fake_connect)
    await schema._ensure_database('postgresql://u:p@host/papaya')

    assert not any('CREATE DATABASE' in query for query in conn.queries)


async def test_ensure_database_tolerates_parallel_creation(monkeypatch):
    """``CREATE DATABASE``, проигравший гонку, не роняет старт.

    Второй процесс (web/celery) мог создать ту же базу между проверкой первого
    и его ``CREATE``. Ошибка ``DuplicateDatabaseError`` — ожидаемый исход.
    """
    conn = _FakeConn(
        exists=False,
        create_error=asyncpg.exceptions.DuplicateDatabaseError('already exists'),
    )

    async def fake_connect(dsn):
        return conn

    monkeypatch.setattr(asyncpg, 'connect', fake_connect)
    await schema._ensure_database('postgresql://u:p@host/papaya')

    assert any('CREATE DATABASE' in query for query in conn.queries)


async def test_migration_decision_uses_state_read_under_lock(monkeypatch):
    """Решение принимается по состоянию, снятому под блокировкой.

    Снимок «схема без ``alembic_version``» успел устареть: пока процесс ждал
    блокировку, другой уже довёл базу до head. Скрипт обязан увидеть актуальную
    схему и не закреплять baseline повторно (``stamp 0001``).
    """
    queries: list[str] = []
    calls: list[tuple] = []

    class _LockConn(_FakeConn):
        async def execute(self, query, *args):
            queries.append(query)

    conn = _LockConn()

    async def fake_connect(dsn):
        return conn

    async def fake_ensure(dsn):
        return None

    async def fake_read_state(connection):
        return (True, True)

    def fake_alembic(*args):
        calls.append(args)

    monkeypatch.setattr(asyncpg, 'connect', fake_connect)
    monkeypatch.setattr(schema, '_ensure_database', fake_ensure)
    monkeypatch.setattr(schema, '_read_state', fake_read_state)
    monkeypatch.setattr(schema, '_alembic', fake_alembic)

    await schema._run_migrations_locked()

    assert ('upgrade', 'head') in calls
    assert ('stamp', schema.BASELINE_REVISION) not in calls
    assert any('pg_advisory_lock' in query for query in queries)
    assert any('pg_advisory_unlock' in query for query in queries)
