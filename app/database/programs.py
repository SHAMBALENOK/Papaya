"""Слой доступа к образовательным программам вуза (ТЗ §4.1).

Программы используются как область действия правила льготы и как фильтр.
Программы принадлежат вузу; дубликаты внутри одного вуза невозможны
(уникальный индекс по ``(university_id, name_norm)``).
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.middlewares.serializers import program_to_dict
from app.models.programs import UniversityProgram


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def list_programs(university_id) -> list[dict]:
    """Программы вуза по алфавиту."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UniversityProgram)
            .where(UniversityProgram.university_id == _as_uuid(university_id))
            .order_by(UniversityProgram.name_norm, UniversityProgram.id)
        )
        return [program_to_dict(item) for item in result.scalars().all()]


async def add_program(university_id, name: str, description: str | None = None) -> dict | None:
    """Добавить программу вузу.

    ``name_norm`` считается сервером; дубликат внутри вуза возвращает ``None``.
    """
    name = (name or '').strip()
    name_norm = normalize_name(name)
    if not name_norm:
        return None

    program = UniversityProgram(
        university_id=_as_uuid(university_id),
        name=name,
        name_norm=name_norm,
        description=description,
    )
    async with AsyncSessionLocal() as session:
        session.add(program)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(program)
        return program_to_dict(program)


async def remove_program(university_id, program_id) -> bool:
    """Удалить программу, если она принадлежит этому вузу."""
    async with AsyncSessionLocal() as session:
        program = (
            await session.execute(
                select(UniversityProgram).where(
                    UniversityProgram.id == _as_uuid(program_id),
                    UniversityProgram.university_id == _as_uuid(university_id),
                )
            )
        ).scalar_one_or_none()
        if program is None:
            return False
        await session.delete(program)
        await session.commit()
        return True


async def replace_programs(university_id, names: list[str]) -> list[dict]:
    """Заменить набор программ вуза переданным списком.

    Используется при массовой правке из панели: набор задаётся целиком, а не
    инкрементально. Пустые и повторяющиеся названия отбрасываются.
    """
    seen: set[str] = set()
    cleaned: list[tuple[str, str]] = []
    for raw in names or []:
        name = (raw or '').strip()
        key = normalize_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append((name, key))

    university_uuid = _as_uuid(university_id)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(UniversityProgram).where(
                    UniversityProgram.university_id == university_uuid
                )
            )
        ).scalars().all()
        existing_by_key = {item.name_norm: item for item in existing}

        for name, key in cleaned:
            program = existing_by_key.pop(key, None)
            if program is not None:
                program.name = name
                program.updatedAt = now
            else:
                session.add(
                    UniversityProgram(
                        university_id=university_uuid,
                        name=name,
                        name_norm=key,
                    )
                )
        # Всё, что осталось в existing_by_key, в новом наборе отсутствует.
        for program in existing_by_key.values():
            await session.delete(program)
        await session.commit()

        result = await session.execute(
            select(UniversityProgram)
            .where(UniversityProgram.university_id == university_uuid)
            .order_by(UniversityProgram.name_norm, UniversityProgram.id)
        )
        return [program_to_dict(item) for item in result.scalars().all()]
