import bcrypt
from datetime import datetime, timezone
from sqlalchemy import select, func
from app.database.database import AsyncSessionLocal
from app.models.users import Users
from app.middlewares.serializers import user_to_dict
from app.middlewares.task_queue import task_queue, AsyncCeleryTask
import uuid as uuid_mod

DB_TASK_OPTIONS = dict(
    base=AsyncCeleryTask,
    time_limit=10,
    default_retry_delay=2,
    retry_backoff=True,
    retry_backoff_max=6,
    queue="heavy",
)


def _full_user_dict(user) -> dict:
    """
    Сериализация пользователя вместе с хэшем пароля.

    Пароль нужен при входе (проверка пароля), поэтому в отличие от
    user_to_dict() он сохраняется в результате задачи.
    """
    data = user_to_dict(user)
    data['password'] = user.password
    return data


@task_queue.task(**DB_TASK_OPTIONS)
async def add_user(ins: dict):
    """
    Функция для создания пользователя в базе данных
    """
    salt = bcrypt.gensalt(rounds=12)
    user = Users(
        name=ins.get('name'),
        surname=ins.get('surname'),
        email=ins.get('email'),
        password=bcrypt.hashpw(ins.get('password').encode('utf-8'), salt).decode('utf-8'),
    )
    async with AsyncSessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user_to_dict(user)


@task_queue.task(**DB_TASK_OPTIONS)
async def find_user_by_email(email: str):
    """
    Функция для поиска пользователя по email
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.email == email)
        )
        user = result.scalars().first()
        return _full_user_dict(user) if user else None


@task_queue.task(**DB_TASK_OPTIONS)
async def find_user_by_id(user_id: str):
    """
    Функция для поиска пользователя по id
    """
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()
        return user_to_dict(user) if user else None


@task_queue.task(**DB_TASK_OPTIONS)
async def edit_user(user_id: str, ins: dict):
    """
    Функция редактирования данных
    """
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


@task_queue.task(**DB_TASK_OPTIONS)
async def get_amount_of_users() -> int:
    """
    Функция показывающая количество пользователей
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Users)
        )
        return result.scalar()


@task_queue.task(**DB_TASK_OPTIONS)
async def show_random_users(quantity: int):
    """
    Функция для показа пользователей
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.isActive == True).limit(quantity)
        )
        return [user_to_dict(user) for user in result.scalars().all()]
