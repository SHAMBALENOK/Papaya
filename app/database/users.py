import uuid as uuid_mod
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import user_to_dict
from app.models.users import Users


def _full_user_dict(user) -> dict:
    """Сериализовать пользователя вместе с хэшем пароля для входа."""
    data = user_to_dict(user)
    data['password'] = user.password
    return data


async def add_user(ins: dict):
    """Создать пользователя в базе данных.

    Возвращает ``None``, если такой email уже существует (закрывает гонку
    двух одновременных регистраций: между SELECT и INSERT мог появиться второй
    пользователь с тем же адресом).
    """
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
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
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


# Поля, которые разрешено менять через edit_user. Пароль сознательно не входит:
# смена пароля должна проходить отдельный путь с хешированием, а не setattr.
# id, createdAt и updatedAt задаёт сервер. organization_id — максимум одна
# организация, владелец которой может быть привязан через отдельный сервисный
# путь (например, promotion), поэтому поле по умолчанию доступно админу.
_USER_EDITABLE_FIELDS = frozenset({
    'name', 'surname', 'email', 'gender', 'bday', 'bio', 'phone',
    'country', 'region', 'status', 'role', 'isActive',
    'organization_id', 'metadata',
})


async def edit_user(user_id: str, ins: dict):
    """Изменить данные пользователя.

    Применяются только поля из allowlist ``_USER_EDITABLE_FIELDS``; остальное
    игнорируется. ``updatedAt`` перезаписывается сервером.
    """
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalars().first()
        if not user:
            return None
        for key, value in ins.items():
            if key in _USER_EDITABLE_FIELDS:
                if key in ('metadata',):
                    user.metadata_ = value
                elif key in ('organization_id',):
                    user.organization_id = (
                        uuid_mod.UUID(value) if value else None
                    )
                else:
                    setattr(user, key, value)
        user.updatedAt = now
        try:
            await session.commit()
        except IntegrityError:
            # Email-unique конфликт (гонка двух одновременных обновлений).
            # Транзакция после исключения не должна оставаться «сломанной»:
            # явный rollback, затем пробрасываем наверх для HTTP 409.
            await session.rollback()
            raise
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