"""Настройка асинхронной базы данных SQLAlchemy.

Единственный источник истины для схемы — миграции Alembic (запускаются
скриптом ``scripts/ensure_db_schema.py`` из точки входа контейнера). Явного
создания таблиц через ``Base.metadata.create_all`` на старте приложения больше
нет: иначе схема на production и в тестах разъезжается с миграциями.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError(
        'DATABASE_URL is not set. Set it (e.g. '
        'postgresql+asyncpg://user:pass@host:5432/db) before starting the app.'
    )

# NullPool: каждая задача/запрос получает своё соединение; пул не переживает
# разные event loop'ы (Celery asyncio.run).
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI-зависимость: одна сессия на запрос.

    Сессия открывается в ``async with``, поэтому при исключении автоматически
    откатывается, а после успешного ответа — закрывается.
    """
    async with AsyncSessionLocal() as db:
        yield db


def get_connection_url() -> str | None:
    """Вернуть текущий DATABASE_URL (для диагностики и тестов)."""
    return DATABASE_URL


@asynccontextmanager
async def db_lifespan(app: FastAPI):
    """Lifespan базы данных: здесь нет создания схемы.

    Схема создаётся и обновляется миграциями Alembic до старта gunicorn
    (см. scripts/ensure_db_schema.py внутри setup.sh).
    """
    yield