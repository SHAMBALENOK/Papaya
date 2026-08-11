from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import asyncio
import os
from app.database.base import Base
from contextlib import asynccontextmanager
from fastapi import FastAPI

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://', 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=300,  # Переподключение через 5 минут
    pool_size=5,
    max_overflow=10
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

@asynccontextmanager
async def db_lifespan(app: FastAPI):
    if os.environ.get("GUNICORN_WORKER_ID", "0") == "0":
        try:
            await init_models()
        except Exception:
            pass
    yield