from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
import os

DATABASE_URL = os.getenv('DATABASE_URL') #сделать автоматическую замену способа на +aio..

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

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db