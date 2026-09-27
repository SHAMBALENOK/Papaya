"""Слой доступа к каталогу университетов.

Каталог читается публично: школьник смотрит вузы и их БВИ-олимпиады без
регистрации. Пишет каталог администратор (см. ``app/routers/universities.py``),
а представитель университета управляет только связями своего вуза.

Сортировка — по алфавиту: каталог вузов читают списком, а не по дате
добавления.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import comparable_text_sql, like_pattern, normalize_name
from app.middlewares.serializers import university_to_dict
from app.models.universities import Universities


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _searchable(column):
    """Текст поля в виде, сопоставимом с запросом пользователя.

    Сравнение регистронезависимое (ILIKE), поэтому сам шаблон поиска
    приводить к нижнему регистру не нужно.
    """
    return comparable_text_sql(column)


async def get_university(university_id) -> dict | None:
    """Найти университет по id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Universities).where(
                Universities.id == _as_uuid(university_id)
            )
        )
        university = result.scalar_one_or_none()
        return university_to_dict(university) if university else None


async def find_university_by_name_norm(name_norm: str) -> dict | None:
    """Точный поиск университета по нормализованному названию."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Universities).where(Universities.name_norm == name_norm)
        )
        university = result.scalar_one_or_none()
        return university_to_dict(university) if university else None


async def list_universities(
    *,
    search: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Список университетов с необязательным поиском.

    ``search`` ищет по полному названию, краткому названию и описанию:
    пользователь ищет «МФТИ», «ИТМО» или «Университет ИТМО» — и хочет найти
    один и тот же вуз. Регистр не учитывается, переводы строк в описании
    схлопываются (см. ``comparable_text``).
    """
    statement = select(Universities)
    query = (search or '').strip()
    if query:
        pattern = like_pattern(query)
        statement = statement.where(
            _searchable(Universities.name).ilike(pattern, escape='\\')
            | _searchable(Universities.short_name).ilike(pattern, escape='\\')
            | _searchable(Universities.description).ilike(pattern, escape='\\')
        )
    statement = statement.order_by(Universities.name_norm, Universities.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [university_to_dict(item) for item in result.scalars().all()]


async def add_university(ins: dict) -> dict | None:
    """Создать университет.

    ``name_norm`` вычисляется сервером. Если вуз с таким нормализованным
    названием уже есть, возвращается ``None``: каталог не должен содержать
    два одинаковых университета.
    """
    name = (ins.get('name') or '').strip()
    name_norm = normalize_name(name)
    if not name_norm:
        return None

    university = Universities(
        name=name,
        name_norm=name_norm,
        short_name=ins.get('short_name'),
        description=ins.get('description'),
        website=ins.get('website'),
        image=ins.get('image'),
    )
    async with AsyncSessionLocal() as session:
        session.add(university)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(university)
        return university_to_dict(university)


_UNIVERSITY_EDITABLE_FIELDS = frozenset({
    'name', 'short_name', 'description', 'website', 'image',
})


async def edit_university(university_id, ins: dict) -> dict | None:
    """Изменить университет.

    Применяются только поля из allowlist ``_UNIVERSITY_EDITABLE_FIELDS``.
    При смене названия ``name_norm`` пересчитывается, поэтому поиск дубликатов
    продолжает работать.
    """
    university_uuid = _as_uuid(university_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Universities).where(Universities.id == university_uuid)
        )
        university = result.scalar_one_or_none()
        if not university:
            return None

        for key, value in ins.items():
            if key not in _UNIVERSITY_EDITABLE_FIELDS:
                continue
            if key == 'name':
                name = (value or '').strip()
                if not name:
                    continue
                university.name = name
                university.name_norm = normalize_name(name)
                continue
            setattr(university, key, value)

        university.updatedAt = datetime.now(timezone.utc)
        try:
            await session.commit()
        except IntegrityError:
            # name_norm уникален: вуз с таким названием уже есть.
            await session.rollback()
            return None
        await session.refresh(university)
        return university_to_dict(university)


async def delete_university(university_id) -> bool:
    """Удалить университет вместе с его связями БВИ (ON DELETE CASCADE)."""
    university_uuid = _as_uuid(university_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Universities).where(Universities.id == university_uuid)
        )
        university = result.scalar_one_or_none()
        if not university:
            return False
        await session.delete(university)
        await session.commit()
        return True


async def count_universities() -> int:
    """Количество университетов в каталоге."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Universities)
        )
        return result.scalar()
