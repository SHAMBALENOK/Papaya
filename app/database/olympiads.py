"""Слой доступа к каталогу олимпиад.

Олимпиада — единая каноническая сущность: одна запись на олимпиаду
независимо от года. Каталог читается публично, создаётся и правится
администратором вручную или через импорт документов РСОШ
(см. ``app/rsosh``).

``name_norm`` нормализуется сервером: он же используется для поиска
дубликатов при импорте (см. ``app/rsosh/matching.py``).

Физического удаления олимпиады здесь нет и не должно появляться: у записи
есть история (подтверждённые связи БВИ, документ-источник, путь по перечню
РСОШ), а удаление уничтожило бы её вместе с подтверждёнными заявками
университетов. Единственный способ убрать олимпиаду из актуальных —
архивирование (см. ``app/routers/admin.py``).
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import comparable_text_sql, like_pattern, normalize_name
from app.middlewares.serializers import olympiad_to_dict
from app.models.olympiads import Olympiads


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _searchable(column):
    """Текст поля в виде, сопоставимом с запросом пользователя.

    Сравнение регистронезависимое (ILIKE), поэтому сам шаблон поиска
    приводить к нижнему регистру не нужно.
    """
    return comparable_text_sql(column)


async def get_olympiad(olympiad_id) -> dict | None:
    """Найти олимпиаду по id, включая архивные."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads).where(Olympiads.id == _as_uuid(olympiad_id))
        )
        olympiad = result.scalar_one_or_none()
        return olympiad_to_dict(olympiad) if olympiad else None


async def list_olympiads(
    *,
    status: str | None = None,
    search: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Список олимпиад каталога.

    ``status`` — фильтр актуальности (``PUBLISHED`` по умолчанию в HTTP-слое,
    ``None`` означает «все», включая архивные: так админ видит полный каталог).
    ``search`` ищет по названию и описанию без учёта регистра; при поиске
    каталог сортируется по алфавиту, иначе остаётся порядок добавления.
    """
    statement = select(Olympiads)
    if status is not None:
        statement = statement.where(Olympiads.status == status)
    query = (search or '').strip()
    if query:
        pattern = like_pattern(query)
        statement = statement.where(
            _searchable(Olympiads.name).ilike(pattern, escape='\\')
            | _searchable(Olympiads.description).ilike(pattern, escape='\\')
        )
    if query:
        statement = statement.order_by(Olympiads.name_norm, Olympiads.id)
    else:
        statement = statement.order_by(Olympiads.createdAt.desc(), Olympiads.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [olympiad_to_dict(item) for item in result.scalars().all()]


async def add_olympiad(ins: dict) -> dict | None:
    """Создать олимпиаду (``name_norm`` вычисляется сервером)."""
    name = (ins.get('name') or '').strip()
    name_norm = normalize_name(name)
    if not name_norm:
        return None

    status = ins.get('status') or 'PUBLISHED'
    olympiad = Olympiads(
        name=name,
        name_norm=name_norm,
        description=ins.get('description'),
        official_url=ins.get('official_url'),
        preview_image=ins.get('preview_image'),
        image=ins.get('image'),
        source_url=ins.get('source_url'),
        source_doc_id=_as_uuid(ins['source_doc_id']) if ins.get('source_doc_id') else None,
        status=status,
    )
    async with AsyncSessionLocal() as session:
        session.add(olympiad)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(olympiad)
        return olympiad_to_dict(olympiad)


_OLYMPIAD_EDITABLE_FIELDS = frozenset({
    'name', 'description', 'official_url', 'preview_image', 'image', 'source_url',
    'source_doc_id', 'status', 'archive_reason',
})


async def edit_olympiad(olympiad_id, ins: dict) -> dict | None:
    """Изменить олимпиаду.

    Применяются только поля из allowlist ``_OLYMPIAD_EDITABLE_FIELDS``;
    ``name_norm`` пересчитывается по поступающему имени.
    """
    olympiad_uuid = _as_uuid(olympiad_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads).where(Olympiads.id == olympiad_uuid)
        )
        olympiad = result.scalar_one_or_none()
        if not olympiad:
            return None

        for key, value in ins.items():
            if key not in _OLYMPIAD_EDITABLE_FIELDS:
                continue
            if key == 'name':
                name = (value or '').strip()
                if not name:
                    continue
                olympiad.name = name
                olympiad.name_norm = normalize_name(name)
                continue
            if key == 'source_doc_id':
                olympiad.source_doc_id = _as_uuid(value) if value else None
                continue
            setattr(olympiad, key, value)

        olympiad.updatedAt = datetime.now(timezone.utc)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(olympiad)
        return olympiad_to_dict(olympiad)
