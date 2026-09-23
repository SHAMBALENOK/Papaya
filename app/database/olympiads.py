import re
import uuid as uuid_mod

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import olympiad_to_dict
from app.models.olympiads import Olympiads


def normalize_name(name: str) -> str:
    """Нормализовать название для точного поиска дубликатов.

    Нижний регистр, сжатие пробелов, трим лишних пробелов. Пунктуация
    сохраняется: для RSOSH-данных она может быть значимой.
    """
    if not name:
        return ''
    return ' '.join(re.sub(r'\s+', ' ', name).strip().lower().split())


async def get_olympiad(olympiad_id: str) -> dict | None:
    """Найти олимпиаду по id, включая архивные."""
    if isinstance(olympiad_id, str):
        olympiad_id = uuid_mod.UUID(olympiad_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads).where(Olympiads.id == olympiad_id)
        )
        olympiad = result.scalar_one_or_none()
        return olympiad_to_dict(olympiad) if olympiad else None


async def list_olympiads(
    *,
    status: str | None = None,
    organizer_id: str | uuid_mod.UUID | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Детерминированный список олимпиад с опциональными фильтрами.

    ``organizer_id`` фильтрует по вхождению организации в
    ``Olympiads.organizer_ids`` (PostgreSQL JSONB containment).
    """
    statement = select(Olympiads)
    if status is not None:
        statement = statement.where(Olympiads.status == status)
    if organizer_id is not None:
        if isinstance(organizer_id, str):
            organizer_id = str(uuid_mod.UUID(organizer_id))
        else:
            organizer_id = str(organizer_id)
        statement = statement.where(
            Olympiads.organizer_ids.op('@>')([organizer_id])
        )
    statement = statement.order_by(Olympiads.created_at.desc(), Olympiads.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [olympiad_to_dict(olympiad) for olympiad in result.scalars().all()]


async def find_olympiad_by_name_norm(name_norm: str) -> dict | None:
    """Точный поиск олимпиады по нормализованному названию (для matching)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads).where(Olympiads.name_norm == name_norm)
        )
        olympiad = result.scalar_one_or_none()
        return olympiad_to_dict(olympiad) if olympiad else None


# Поля, которые разрешено менять через edit_olympiad. name_norm, id и
# временные метки вычисляет сервер, их нельзя протащить через setattr.
_OLYMPIAD_EDITABLE_FIELDS = frozenset({
    'name', 'organizer_ids', 'description', 'subjects', 'levels', 'years',
    'profiles', 'bvi_organizations', 'registration_url', 'official_url',
    'status', 'metadata',
})


async def add_olympiad(ins: dict) -> dict:
    """Создать олимпиаду (``name_norm`` вычисляется сервером)."""
    olympiad = Olympiads(
        name=ins.get('name'),
        organizer_ids=list(ins.get('organizer_ids') or []),
        description=ins.get('description'),
        subjects=list(ins.get('subjects') or []),
        levels=list(ins.get('levels') or []),
        years=list(ins.get('years') or []),
        profiles=list(ins.get('profiles') or []),
        bvi_organizations=list(ins.get('bvi_organizations') or []),
        registration_url=ins.get('registration_url'),
        official_url=ins.get('official_url'),
        status=ins.get('status', 'PUBLISHED'),
        name_norm=normalize_name(ins.get('name') or ''),
        metadata_=ins.get('metadata'),
    )
    async with AsyncSessionLocal() as session:
        session.add(olympiad)
        await session.commit()
        await session.refresh(olympiad)
        return olympiad_to_dict(olympiad)


async def edit_olympiad(olympiad_id: str, ins: dict) -> dict | None:
    """Изменить олимпиаду.

    Применяются только поля из allowlist ``_OLYMPIAD_EDITABLE_FIELDS``;
    ``name_norm`` пересчитывается на основе поступающего имени.
    """
    if isinstance(olympiad_id, str):
        olympiad_id = uuid_mod.UUID(olympiad_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads).where(Olympiads.id == olympiad_id)
        )
        olympiad = result.scalar_one_or_none()
        if not olympiad:
            return None
        for key, value in ins.items():
            if key in _OLYMPIAD_EDITABLE_FIELDS:
                if key == 'metadata':
                    olympiad.metadata_ = value
                elif key in ('organizer_ids', 'subjects', 'levels', 'years',
                             'profiles', 'bvi_organizations'):
                    setattr(olympiad, key, list(value or []))
                else:
                    setattr(olympiad, key, value)
        if 'name' in ins:
            olympiad.name_norm = normalize_name(ins['name'] or '')
        await session.commit()
        await session.refresh(olympiad)
        return olympiad_to_dict(olympiad)


async def delete_olympiad(olympiad_id: str) -> bool:
    """Удалить олимпиаду.

    Документы, ссылающиеся на неё через ``docs.olympiad_id``, остаются
    (историческая информация не удаляется автоматически).
    """
    if isinstance(olympiad_id, str):
        olympiad_id = uuid_mod.UUID(olympiad_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads).where(Olympiads.id == olympiad_id)
        )
        olympiad = result.scalar_one_or_none()
        if not olympiad:
            return False
        await session.delete(olympiad)
        await session.commit()
        return True