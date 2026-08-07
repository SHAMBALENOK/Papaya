import bcrypt
from datetime import datetime, timezone
from typing import Callable
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import uuid as uuid_mod


async def add_user(ins: dict, session: AsyncSession, model: Callable):
    """
    Функция для создания пользователя в базе данных
    """
    salt = bcrypt.gensalt(rounds=12)
    user = model(
        name=ins.get('name'),
        surname=ins.get('surname'),
        email=ins.get('email'),
        password=bcrypt.hashpw(ins.get('password').encode('utf-8'), salt).decode('utf-8'),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def find_user_by_email(email: str, session: AsyncSession, model: Callable):
    """
    Функция для поиска пользователя по email
    """
    result = await session.execute(
        select(model).where(model.email == email)
    )
    return result.scalars().first()


async def find_user_by_id(user_id: str, session: AsyncSession, model: Callable):
    """
    Функция для поиска пользователя по id
    """
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    result = await session.execute(
        select(model).where(model.id == user_id)
    )
    return result.scalar_one_or_none()


async def edit_user(user_id: str, ins: dict, session: AsyncSession, model: Callable):
    """
    Функция редактирования данных
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await session.execute(
        select(model).where(model.id == user_id)
    )
    user = result.scalars().first()
    if not user:
        return None
    for key, value in ins.items():
        setattr(user, key, value)
    user.updatedAt = now
    await session.commit()
    await session.refresh(user)
    return user

async def get_amount_of_users(session: AsyncSession, model: Callable) -> int:
    """
    Функция показывающая количество событий
    """
    result = await session.execute(
        select(func.count()).select_from(model)
    )
    return result.scalar()

async def show_random_users(quantity: int, session: AsyncSession, model: Callable):
    """
    Функция для показа событий
    """
    result = await session.execute(
        select(model).where(model.isActive == True).limit(quantity)
    )
    return result.scalars().all()