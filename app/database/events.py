from datetime import datetime, timezone
from typing import Callable
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import uuid as uuid_mod


async def add_event(ins: dict, session: AsyncSession, model: Callable):
    """
    Функция для создания события в базе данных
    """
    event = model(
        name=ins.get('name'),
        disc=ins.get('disc'),
        owner=ins.get('owner'),
        preview_picture=ins.get('preview_picture'),
        picture=ins.get('picture'),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def find_event_by_id(event_id: str, session: AsyncSession, model: Callable):
    """
    Функция для поиска события по id
    """
    result = await session.execute(
        select(model).where(model.id == event_id)
    )
    return result.scalars().first()


async def show_random_events(quantity: int, session: AsyncSession, model: Callable):
    """
    Функция для показа событий
    """
    result = await session.execute(
        select(model).where(model.isActive == True).limit(quantity)
    )
    return result.scalars().all()


async def edit_event(event_id: str, ins: dict, session: AsyncSession, model: Callable):
    """
    Функция для редактирования
    """
    if isinstance(event_id, str):
        event_id = uuid_mod.UUID(event_id)
    result = await session.execute(
        select(model).where(model.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        return None
    for key, value in ins.items():
        setattr(event, key, value)
    event.updatedAt = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(event)
    return event


async def get_amount_of_events(session: AsyncSession, model: Callable) -> int:
    """
    Функция показывающая количество событий
    """
    result = await session.execute(
        select(func.count()).select_from(model)
    )
    return result.scalar()