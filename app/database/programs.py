"""Слой доступа к образовательным программам вуза (ТЗ §4.1).

Программы используются как область действия правила льготы и как фильтр.
Программы принадлежат вузу; дубликаты внутри одного вуза невозможны
(уникальный индекс по ``(university_id, name_norm)``).

Программа, на которую ссылаются правила льгот, не удаляется: внешний ключ
``benefit_rule_programs`` блокирует удаление, а слой данных отдаёт понятную
ошибку. Иначе правило молча теряло бы область действия.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.middlewares.serializers import program_to_dict
from app.models.benefit_rules import BenefitRuleProgram
from app.models.programs import UniversityProgram


class ProgramError(ValueError):
    """Операция с программой невозможна (например, она используется в правилах)."""

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _with_usage():
    """Программы вместе с числом ссылающихся правил — одним запросом."""
    usage = (
        select(
            BenefitRuleProgram.program_id.label('program_id'),
            func.count().label('rules_count'),
        )
        .group_by(BenefitRuleProgram.program_id)
        .subquery()
    )
    return (
        select(UniversityProgram, func.coalesce(usage.c.rules_count, 0))
        .outerjoin(usage, usage.c.program_id == UniversityProgram.id)
    )


async def _list_in_session(session, university_uuid) -> list[dict]:
    result = await session.execute(
        _with_usage()
        .where(UniversityProgram.university_id == university_uuid)
        .order_by(UniversityProgram.name_norm, UniversityProgram.id)
    )
    return [
        {**program_to_dict(item), 'rules_count': int(count)}
        for item, count in result.all()
    ]


async def list_programs(university_id) -> list[dict]:
    """Программы вуза по алфавиту с числом правил, где они используются."""
    async with AsyncSessionLocal() as session:
        return await _list_in_session(session, _as_uuid(university_id))


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
        description=(description or '').strip() or None,
    )
    async with AsyncSessionLocal() as session:
        session.add(program)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(program)
        return {**program_to_dict(program), 'rules_count': 0}


async def remove_program(university_id, program_id) -> bool:
    """Удалить программу, если она принадлежит этому вузу и не используется."""
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
        used = (
            await session.execute(
                select(func.count())
                .select_from(BenefitRuleProgram)
                .where(BenefitRuleProgram.program_id == program.id)
            )
        ).scalar_one()
        if used:
            raise ProgramError(
                f'Программа используется в правилах льгот ({used}): сначала '
                'уберите её из правил или замените другой.'
            )
        await session.delete(program)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise ProgramError(
                'Программа используется в правилах льгот: сначала уберите её из правил.'
            )
        return True


async def replace_programs(university_id, names: list[str]) -> list[dict]:
    """Заменить набор программ вуза переданным списком названий.

    Используется при массовой правке из панели: набор задаётся целиком, а не
    инкрементально. Пустые и повторяющиеся названия отбрасываются. Программы,
    которых нет в новом списке, удаляются — кроме тех, что используются в
    правилах льгот: такие остаются, и вызывающий получает ``ProgramError`` с
    перечнем, чтобы интерфейс не делал вид, что программа исчезла.
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
                _with_usage().where(UniversityProgram.university_id == university_uuid)
            )
        ).all()
        existing_by_key = {item.name_norm: (item, int(count)) for item, count in existing}

        for name, key in cleaned:
            found = existing_by_key.pop(key, None)
            if found is not None:
                program, _count = found
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
        kept_in_use: list[str] = []
        for program, count in existing_by_key.values():
            if count:
                kept_in_use.append(program.name)
                continue
            await session.delete(program)
        await session.commit()

        programs = await _list_in_session(session, university_uuid)
    if kept_in_use:
        raise ProgramError(
            'Часть программ не удалена, потому что используется в правилах льгот: '
            + ', '.join(sorted(kept_in_use))
            + '. Остальные изменения сохранены.',
            status_code=409,
        )
    return programs
