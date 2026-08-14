from datetime import datetime, timezone
from sqlalchemy import select, func
from app.database.database import AsyncSessionLocal
from app.models.events import Events
from app.middlewares.serializers import event_to_dict
import uuid as uuid_mod


async def add_event(ins: dict):
    """
    Функция для создания события в базе данных
    """
    event = Events(
        name=ins.get('name'),
        disc=ins.get('disc'),
        owner=ins.get('owner'),
        preview_picture=ins.get('preview_picture'),
        picture=ins.get('picture'),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as session:
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event_to_dict(event)


async def find_event_by_id(event_id: str):
    """
    Функция для поиска события по id
    """
    if isinstance(event_id, str):
        event_id = uuid_mod.UUID(event_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Events).where(Events.id == event_id)
        )
        event = result.scalars().first()
        return event_to_dict(event) if event else None


async def show_random_events(quantity: int):
    """
    Функция для показа событий
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Events).where(Events.isActive == True).limit(quantity)
        )
        return [event_to_dict(event) for event in result.scalars().all()]


async def edit_event(event_id: str, ins: dict):
    """
    Функция для редактирования
    """
    if isinstance(event_id, str):
        event_id = uuid_mod.UUID(event_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Events).where(Events.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            return None
        for key, value in ins.items():
            setattr(event, key, value)
        event.updatedAt = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(event)
        return event_to_dict(event)


async def get_amount_of_events() -> int:
    """
    Функция показывающая количество событий
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Events)
        )
        return result.scalar()
