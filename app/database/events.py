from datetime import datetime, timezone
import uuid as uuid_mod

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import event_to_dict
from app.models.events import Events


def _make_event(ins: dict, now: datetime) -> Events:
    return Events(
        name=ins.get('name'),
        disc=ins.get('disc'),
        owner=ins.get('owner'),
        preview_picture=ins.get('preview_picture'),
        picture=ins.get('picture'),
        createdAt=now,
        updatedAt=now,
    )


async def add_events(items: list[dict]) -> list[dict]:
    """Создать несколько событий одной атомарной транзакцией."""
    if not items:
        return []

    now = datetime.now(timezone.utc)
    events = [_make_event(ins, now) for ins in items]
    async with AsyncSessionLocal() as session:
        session.add_all(events)
        await session.commit()
        # expire_on_commit=False: сгенерированные UUID и Python-default поля
        # остаются в объектах, дополнительные SELECT для каждой строки не нужны.
        return [event_to_dict(event) for event in events]


async def add_event(ins: dict):
    """Создать одно событие."""
    return (await add_events([ins]))[0]


async def find_event_by_id(event_id: str):
    """Найти событие по id, включая архивное."""
    if isinstance(event_id, str):
        event_id = uuid_mod.UUID(event_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Events).where(Events.id == event_id)
        )
        event = result.scalars().first()
        return event_to_dict(event) if event else None


async def list_events(
    *,
    active_only: bool = True,
    owner: str | uuid_mod.UUID | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Вернуть детерминированный список событий для нужной области кэша."""
    statement = select(Events)
    if active_only:
        statement = statement.where(Events.isActive.is_(True))
    if owner is not None:
        if isinstance(owner, str):
            owner = uuid_mod.UUID(owner)
        statement = statement.where(Events.owner == owner)
    statement = statement.order_by(Events.createdAt.desc(), Events.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [event_to_dict(event) for event in result.scalars().all()]


async def show_random_events(quantity: int):
    """Обратная совместимость: вернуть активные события."""
    return await list_events(active_only=True, limit=quantity)


async def edit_event(event_id: str, ins: dict):
    """Изменить событие."""
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
    """Вернуть общее количество событий, включая архивные."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Events)
        )
        return result.scalar()