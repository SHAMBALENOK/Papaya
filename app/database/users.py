import uuid as uuid_mod
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import user_to_dict
from app.models.users import Users


def _full_user_dict(user) -> dict:
    """Сериализовать пользователя вместе с хэшем пароля для входа."""
    data = user_to_dict(user)
    data['password'] = user.password
    return data


async def add_user(ins: dict):
    """Создать пользователя в базе данных."""
    salt = bcrypt.gensalt(rounds=12)
    user = Users(
        name=ins.get('name'),
        surname=ins.get('surname'),
        email=ins.get('email'),
        password=bcrypt.hashpw(
            ins.get('password').encode('utf-8'),
            salt,
        ).decode('utf-8'),
    )
    async with AsyncSessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user_to_dict(user)


async def find_user_by_email(email: str):
    """Найти пользователя по email (включая хэш пароля)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.email == email)
        )
        user = result.scalars().first()
        return _full_user_dict(user) if user else None


async def find_user_by_id(user_id: str):
    """Найти пользователя по id без выдачи хэша пароля."""
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()
        return user_to_dict(user) if user else None


async def edit_user(user_id: str, ins: dict):
    """Изменить данные пользователя."""
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalars().first()
        if not user:
            return None
        for key, value in ins.items():
            setattr(user, key, value)
        user.updatedAt = now
        await session.commit()
        await session.refresh(user)
        return user_to_dict(user)


async def list_users(
    *,
    include_inactive: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """Вернуть пользователей для публичного или административного списка."""
    statement = select(Users)
    if not include_inactive:
        statement = statement.where(Users.isActive.is_(True))
    statement = statement.order_by(Users.createdAt.desc(), Users.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [user_to_dict(user) for user in result.scalars().all()]


async def get_amount_of_users() -> int:
    """Вернуть общее количество пользователей."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Users)
        )
        return result.scalar()


async def show_random_users(quantity: int):
    """Обратная совместимость: вернуть активных пользователей."""
    return await list_users(include_inactive=False, limit=quantity)