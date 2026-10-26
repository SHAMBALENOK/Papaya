"""Слой доступа к правилам льгот (ТЗ §4.3, §7, §8, §9, §10).

Правило льготы связывает **существующие** записи каталога: университет,
олимпиаду, (необязательно) сезон и профиль олимпиады и набор программ вуза.
Пара «университет — олимпиада» может иметь несколько правил.

Инварианты, которые держит именно этот модуль (а не роутер):

- правило создаётся только для актуальной олимпиады (``PUBLISHED``); сезон
  обязан принадлежать той же олимпиаде, профиль — тому же сезону, программы —
  тому же вузу (это дублируется составными внешними ключами в БД);
- два одинаковых действующих правила невозможны: ключ содержимого
  ``dedup_key`` + частичный уникальный индекс, конфликт отдаётся как 409;
- каждое изменение — новая версия (``benefit_rule_versions``); откат — тоже
  новая версия с пометкой ``is_rollback``; промежуточные версии не удаляются;
- любое содержательное изменение сбрасывает проверку Papaya в ``unverified``
  (кроме случая, когда администратор в том же запросе явно выставляет
  статус); восстановленная версия никогда не получает ``verified``
  автоматически;
- ``verified`` требует официальный документ и ссылку на источник; ``rejected``
  — причину;
- оптимистическая блокировка: при переданном ``expected_version`` расхождение
  с текущим номером версии даёт 409 вместо молчаливой перезаписи;
- публично видны только опубликованные и не отклонённые правила; черновики и
  архив — представителю своего вуза и администратору.
"""

import uuid as uuid_mod
from datetime import date, datetime, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import like_pattern, normalize_name
from app.middlewares.serializers import (
    benefit_rule_to_dict,
    benefit_version_to_dict,
    olympiad_to_dict,
    university_to_dict,
)
from app.models.benefit_rules import (
    BENEFIT_TYPES,
    RULE_STATUS_ARCHIVED,
    RULE_STATUS_DRAFT,
    RULE_STATUS_PUBLISHED,
    RULE_STATUSES,
    VERIFICATION_REJECTED,
    VERIFICATION_STATUSES,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_VERIFIED,
    BenefitRule,
    BenefitRuleProgram,
)
from app.models.benefit_versions import BenefitRuleVersion
from app.models.docs import Docs
from app.models.olympiads import Olympiads
from app.models.programs import UniversityProgram
from app.models.seasons import OlympiadProfile, OlympiadSeason
from app.models.universities import Universities

__all__ = [
    'BENEFIT_TYPES',
    'RULE_STATUSES',
    'VERIFICATION_STATUSES',
    'BenefitRuleError',
    'build_dedup_key',
    'create_rule',
    'update_rule',
    'set_rule_status',
    'delete_rule',
    'set_verification',
    'attach_document',
    'rollback_rule',
    'list_versions',
    'get_rule',
    'list_rules',
    'count_rules',
    'list_olympiads_for_university',
    'count_olympiads_for_university',
    'list_universities_for_olympiad',
    'count_universities_for_olympiad',
    'rule_facets',
    'count_rules_using_program',
    'set_university_confirmation',
]

#: Статус олимпиады, для которого можно заводить новые правила.
OLYMPIAD_ACTIVE_STATUS = 'PUBLISHED'

#: Содержательные поля правила: их изменение создаёт версию и сбрасывает
#: проверку Papaya.
CONTENT_FIELDS = (
    'season_id',
    'profile_id',
    'benefit_type',
    'result_requirement',
    'subject',
    'extra_requirements',
    'source_url',
    'valid_until',
    'source_doc_id',
)

#: Поля, которые восстанавливает откат (программы — отдельно).
ROLLBACK_FIELDS = CONTENT_FIELDS


class BenefitRuleError(ValueError):
    """Операция над правилом невозможна с переданными данными.

    Несёт ``status_code``/``detail``: HTTP-слой подставляет их в ответ без
    собственной логики, поэтому текст правила не дублируется.
    """

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _as_uuid_or_none(value):
    if value in (None, ''):
        return None
    return _as_uuid(value)


def _iso(value):
    return value.isoformat() if value else None


def build_dedup_key(
    *,
    season_id,
    profile_id,
    benefit_type: str,
    result_requirement: str | None,
    subject: str | None,
    program_ids,
) -> str:
    """Детерминированный ключ содержимого правила.

    Два правила одной пары (вуз, олимпиада) с одинаковым ключом — дубликат.
    Формула продублирована в миграции 0013 для уже существующих строк.
    """
    programs = ','.join(sorted(str(item) for item in program_ids)) or '-'
    return '|'.join(
        [
            str(season_id) if season_id else '-',
            str(profile_id) if profile_id else '-',
            benefit_type or 'BVI',
            normalize_name(result_requirement or '') or '-',
            normalize_name(subject or '') or '-',
            programs,
        ]
    )


# ----------------------------------------------------------------------------
# Чтение
# ----------------------------------------------------------------------------


def _public_only(statement):
    """Публичная видимость: опубликовано и не отклонено проверкой."""
    return statement.where(
        BenefitRule.status == RULE_STATUS_PUBLISHED,
        BenefitRule.verification_status != VERIFICATION_REJECTED,
    )


def _apply_filters(
    statement,
    *,
    university_id=None,
    olympiad_id=None,
    season_id=None,
    profile_id=None,
    program_id=None,
    benefit_type: str | None = None,
    subject: str | None = None,
    verification_status: str | None = None,
    statuses=None,
    public_only: bool = True,
    search: str | None = None,
    olympiad_status: str | None = None,
):
    """Общие фильтры правил: список и подсчёт используют одну функцию.

    Иначе ``total`` расходился бы с реально отдаваемыми строками.
    """
    if university_id is not None:
        statement = statement.where(BenefitRule.university_id == _as_uuid(university_id))
    if olympiad_id is not None:
        statement = statement.where(BenefitRule.olympiad_id == _as_uuid(olympiad_id))
    if season_id is not None:
        statement = statement.where(BenefitRule.season_id == _as_uuid(season_id))
    if profile_id is not None:
        statement = statement.where(BenefitRule.profile_id == _as_uuid(profile_id))
    if program_id is not None:
        statement = statement.where(
            exists().where(
                BenefitRuleProgram.rule_id == BenefitRule.id,
                BenefitRuleProgram.program_id == _as_uuid(program_id),
            )
        )
    if benefit_type is not None:
        statement = statement.where(BenefitRule.benefit_type == benefit_type)
    if subject is not None:
        statement = statement.where(
            func.lower(func.trim(BenefitRule.subject)) == subject.strip().lower()
        )
    if verification_status is not None:
        statement = statement.where(BenefitRule.verification_status == verification_status)
    if statuses:
        statement = statement.where(BenefitRule.status.in_(list(statuses)))
    if public_only:
        statement = _public_only(statement)
    if olympiad_status is not None:
        statement = statement.where(
            BenefitRule.olympiad_id.in_(
                select(Olympiads.id).where(Olympiads.status == olympiad_status)
            )
        )
    if search:
        pattern = like_pattern(search)
        statement = statement.where(
            or_(
                BenefitRule.university_id.in_(
                    select(Universities.id).where(
                        or_(
                            Universities.name.ilike(pattern, escape='\\'),
                            Universities.short_name.ilike(pattern, escape='\\'),
                        )
                    )
                ),
                BenefitRule.olympiad_id.in_(
                    select(Olympiads.id).where(Olympiads.name.ilike(pattern, escape='\\'))
                ),
            )
        )
    return statement


def _enriched_select():
    """Правило вместе с названиями связанных сущностей одним запросом.

    Университет, олимпиада, сезон, профиль и документ подтягиваются JOIN-ами,
    а не отдельными чтениями на строку: иначе на N правил уходило бы 5N+1
    запросов.
    """
    return (
        select(
            BenefitRule,
            Universities.name,
            Universities.short_name,
            Olympiads.name,
            Olympiads.status,
            OlympiadSeason.year,
            OlympiadSeason.label,
            OlympiadSeason.state,
            OlympiadProfile.name,
            OlympiadProfile.subject,
            Docs.name,
            Docs.storage_key,
            Docs.availability,
            Docs.source_url,
        )
        .join(Universities, BenefitRule.university_id == Universities.id)
        .join(Olympiads, BenefitRule.olympiad_id == Olympiads.id)
        .outerjoin(OlympiadSeason, BenefitRule.season_id == OlympiadSeason.id)
        .outerjoin(OlympiadProfile, BenefitRule.profile_id == OlympiadProfile.id)
        .outerjoin(Docs, BenefitRule.source_doc_id == Docs.id)
    )


async def _programs_by_rule(session, rule_ids) -> dict[str, list[dict]]:
    """Программы для набора правил одним запросом."""
    if not rule_ids:
        return {}
    result = await session.execute(
        select(
            BenefitRuleProgram.rule_id,
            UniversityProgram.id,
            UniversityProgram.name,
        )
        .join(UniversityProgram, UniversityProgram.id == BenefitRuleProgram.program_id)
        .where(BenefitRuleProgram.rule_id.in_(list(rule_ids)))
        .order_by(UniversityProgram.name_norm, UniversityProgram.id)
    )
    grouped: dict[str, list[dict]] = {}
    for rule_id, program_id, name in result.all():
        grouped.setdefault(str(rule_id), []).append(
            {'id': str(program_id), 'name': name}
        )
    return grouped


def _row_to_dict(row, programs: list[dict]) -> dict:
    (
        rule,
        university_name,
        university_short_name,
        olympiad_name,
        olympiad_status,
        season_year,
        season_label,
        season_state,
        profile_name,
        profile_subject,
        doc_name,
        doc_storage_key,
        doc_availability,
        doc_source_url,
    ) = row
    data = benefit_rule_to_dict(rule)
    data.update(
        {
            'university_name': university_name,
            'university_short_name': university_short_name,
            'olympiad_name': olympiad_name,
            'olympiad_status': olympiad_status,
            # Правило историческое, если олимпиады больше нет в актуальном
            # перечне: университет давал льготу, пока олимпиада была в РСОШ.
            'is_historical': olympiad_status != OLYMPIAD_ACTIVE_STATUS,
            'season': (
                {
                    'id': data['season_id'],
                    'year': season_year,
                    'label': season_label or str(season_year),
                    'state': season_state,
                }
                if data['season_id']
                else None
            ),
            'profile': (
                {
                    'id': data['profile_id'],
                    'name': profile_name,
                    'subject': profile_subject,
                }
                if data['profile_id']
                else None
            ),
            'document': (
                {
                    'id': data['source_doc_id'],
                    'name': doc_name,
                    'has_file': bool(doc_storage_key),
                    'availability': doc_availability or 'unknown',
                    'source_url': doc_source_url,
                }
                if data['source_doc_id']
                else None
            ),
            'programs': programs,
            'program_ids': [item['id'] for item in programs],
        }
    )
    return data


async def _fetch_enriched(session, statement) -> list[dict]:
    rows = (await session.execute(statement)).all()
    programs = await _programs_by_rule(session, [row[0].id for row in rows])
    return [_row_to_dict(row, programs.get(str(row[0].id), [])) for row in rows]


async def get_rule(rule_id, *, university_id=None) -> dict | None:
    """Правило со связанными сущностями; ``None``, если его нет."""
    statement = _enriched_select().where(BenefitRule.id == _as_uuid(rule_id))
    if university_id is not None:
        statement = statement.where(BenefitRule.university_id == _as_uuid(university_id))
    async with AsyncSessionLocal() as session:
        items = await _fetch_enriched(session, statement)
        return items[0] if items else None


async def list_rules(
    *,
    limit: int | None = None,
    offset: int = 0,
    order: str = 'name',
    **filters,
) -> list[dict]:
    """Список правил с фильтрами и постраничной выдачей (на уровне СУБД)."""
    statement = _apply_filters(_enriched_select(), **filters)
    if order == 'recent':
        statement = statement.order_by(BenefitRule.updatedAt.desc(), BenefitRule.id)
    else:
        statement = statement.order_by(
            Universities.name_norm,
            Olympiads.name_norm,
            OlympiadSeason.year.desc().nulls_last(),
            BenefitRule.createdAt,
            BenefitRule.id,
        )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    async with AsyncSessionLocal() as session:
        return await _fetch_enriched(session, statement)


async def count_rules(**filters) -> int:
    statement = _apply_filters(select(func.count()).select_from(BenefitRule), **filters)
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


async def list_olympiads_for_university(
    university_id,
    *,
    limit: int | None = None,
    offset: int = 0,
    **filters,
) -> list[dict]:
    """Олимпиады, по которым у вуза есть правила, с вложенными правилами.

    Страница считается по олимпиадам (а не по правилам): карточка каталога —
    это олимпиада со списком её условий. Два запроса на страницу: список
    олимпиад и все их правила под тем же фильтром.
    """
    filters = {**filters, 'university_id': university_id}
    matching = _apply_filters(select(BenefitRule.olympiad_id), **filters)
    statement = (
        select(Olympiads)
        .where(Olympiads.id.in_(matching))
        .order_by(Olympiads.name_norm, Olympiads.id)
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    async with AsyncSessionLocal() as session:
        olympiads = (await session.execute(statement)).scalars().all()
        if not olympiads:
            return []
        rules_statement = _apply_filters(_enriched_select(), **filters).where(
            BenefitRule.olympiad_id.in_([item.id for item in olympiads])
        ).order_by(
            OlympiadSeason.year.desc().nulls_last(), BenefitRule.createdAt, BenefitRule.id
        )
        rules = await _fetch_enriched(session, rules_statement)
    grouped: dict[str, list[dict]] = {}
    for rule in rules:
        grouped.setdefault(rule['olympiad_id'], []).append(rule)
    return [
        {
            **olympiad_to_dict(olympiad),
            'is_historical': olympiad.status != OLYMPIAD_ACTIVE_STATUS,
            'rules': grouped.get(str(olympiad.id), []),
        }
        for olympiad in olympiads
    ]


async def count_olympiads_for_university(university_id, **filters) -> int:
    filters = {**filters, 'university_id': university_id}
    statement = _apply_filters(
        select(func.count(func.distinct(BenefitRule.olympiad_id))), **filters
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


async def list_universities_for_olympiad(
    olympiad_id,
    *,
    limit: int | None = None,
    offset: int = 0,
    **filters,
) -> list[dict]:
    """Университеты с правилами по олимпиаде (обратная сторона), с правилами."""
    filters = {**filters, 'olympiad_id': olympiad_id}
    matching = _apply_filters(select(BenefitRule.university_id), **filters)
    statement = (
        select(Universities)
        .where(Universities.id.in_(matching))
        .order_by(Universities.name_norm, Universities.id)
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    async with AsyncSessionLocal() as session:
        olympiad_status = (
            await session.execute(
                select(Olympiads.status).where(Olympiads.id == _as_uuid(olympiad_id))
            )
        ).scalar_one_or_none()
        universities = (await session.execute(statement)).scalars().all()
        if not universities:
            return []
        rules_statement = _apply_filters(_enriched_select(), **filters).where(
            BenefitRule.university_id.in_([item.id for item in universities])
        ).order_by(
            OlympiadSeason.year.desc().nulls_last(), BenefitRule.createdAt, BenefitRule.id
        )
        rules = await _fetch_enriched(session, rules_statement)
    grouped: dict[str, list[dict]] = {}
    for rule in rules:
        grouped.setdefault(rule['university_id'], []).append(rule)
    return [
        {
            **university_to_dict(university),
            'is_historical': olympiad_status != OLYMPIAD_ACTIVE_STATUS,
            'rules': grouped.get(str(university.id), []),
        }
        for university in universities
    ]


async def count_universities_for_olympiad(olympiad_id, **filters) -> int:
    filters = {**filters, 'olympiad_id': olympiad_id}
    statement = _apply_filters(
        select(func.count(func.distinct(BenefitRule.university_id))), **filters
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


async def rule_facets(*, university_id=None, olympiad_id=None, public_only=True) -> dict:
    """Значения для фильтров: виды льгот, предметы, программы, сезоны.

    Считается по СУБД (GROUP BY), а не по загруженной странице: при серверной
    постраничной выдаче клиент видит не все правила и не смог бы собрать
    полный список значений сам.
    """
    base_filters = {
        'university_id': university_id,
        'olympiad_id': olympiad_id,
        'public_only': public_only,
    }
    async with AsyncSessionLocal() as session:
        types = (
            await session.execute(
                _apply_filters(
                    select(BenefitRule.benefit_type, func.count()).group_by(
                        BenefitRule.benefit_type
                    ),
                    **base_filters,
                ).order_by(BenefitRule.benefit_type)
            )
        ).all()
        subjects = (
            await session.execute(
                _apply_filters(
                    select(func.trim(BenefitRule.subject), func.count())
                    .where(BenefitRule.subject.isnot(None), func.trim(BenefitRule.subject) != '')
                    .group_by(func.trim(BenefitRule.subject)),
                    **base_filters,
                ).order_by(func.trim(BenefitRule.subject))
            )
        ).all()
        programs = (
            await session.execute(
                _apply_filters(
                    select(UniversityProgram.id, UniversityProgram.name, func.count())
                    .join(BenefitRuleProgram, BenefitRuleProgram.program_id == UniversityProgram.id)
                    .join(BenefitRule, BenefitRule.id == BenefitRuleProgram.rule_id)
                    .group_by(UniversityProgram.id, UniversityProgram.name, UniversityProgram.name_norm),
                    **base_filters,
                ).order_by(UniversityProgram.name_norm)
            )
        ).all()
        seasons = (
            await session.execute(
                _apply_filters(
                    select(
                        OlympiadSeason.id,
                        OlympiadSeason.year,
                        OlympiadSeason.label,
                        OlympiadSeason.state,
                        func.count(),
                    )
                    .join(BenefitRule, BenefitRule.season_id == OlympiadSeason.id)
                    .group_by(
                        OlympiadSeason.id,
                        OlympiadSeason.year,
                        OlympiadSeason.label,
                        OlympiadSeason.state,
                    ),
                    **base_filters,
                ).order_by(OlympiadSeason.year.desc())
            )
        ).all()
    return {
        'benefit_types': [{'value': value, 'count': count} for value, count in types],
        'subjects': [{'value': value, 'count': count} for value, count in subjects],
        'programs': [
            {'id': str(program_id), 'name': name, 'count': count}
            for program_id, name, count in programs
        ],
        'seasons': [
            {
                'id': str(season_id),
                'year': year,
                'label': label or str(year),
                'state': state,
                'count': count,
            }
            for season_id, year, label, state, count in seasons
        ],
    }


async def count_rules_using_program(program_id) -> int:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(BenefitRuleProgram)
                .where(BenefitRuleProgram.program_id == _as_uuid(program_id))
            )
        ).scalar_one()


# ----------------------------------------------------------------------------
# Запись
# ----------------------------------------------------------------------------


def _validate_enums(data: dict) -> None:
    if 'benefit_type' in data and data['benefit_type'] not in BENEFIT_TYPES:
        raise BenefitRuleError(
            'Недопустимый вид льготы. Разрешены: ' + ', '.join(BENEFIT_TYPES) + '.',
            status_code=400,
        )
    if (
        'verification_status' in data
        and data['verification_status'] not in VERIFICATION_STATUSES
    ):
        raise BenefitRuleError(
            'Недопустимый статус проверки. Разрешены: '
            + ', '.join(VERIFICATION_STATUSES)
            + '.',
            status_code=400,
        )


async def _check_season_and_profile(session, *, olympiad_id, season_id, profile_id) -> None:
    """Сезон — той же олимпиады, профиль — того же сезона (иначе 400/404).

    Составные внешние ключи поймали бы ошибку и так, но человеку нужен
    понятный ответ, а не текст ограничения БД.
    """
    if profile_id is not None and season_id is None:
        raise BenefitRuleError(
            'Профиль указывается вместе с сезоном, которому он принадлежит',
            status_code=400,
        )
    if season_id is not None:
        season_olympiad = (
            await session.execute(
                select(OlympiadSeason.olympiad_id).where(OlympiadSeason.id == season_id)
            )
        ).scalar_one_or_none()
        if season_olympiad is None:
            raise BenefitRuleError('Сезон не найден', status_code=404)
        if season_olympiad != olympiad_id:
            raise BenefitRuleError(
                'Сезон относится к другой олимпиаде', status_code=400
            )
    if profile_id is not None:
        profile_season = (
            await session.execute(
                select(OlympiadProfile.season_id).where(OlympiadProfile.id == profile_id)
            )
        ).scalar_one_or_none()
        if profile_season is None:
            raise BenefitRuleError('Профиль не найден', status_code=404)
        if profile_season != season_id:
            raise BenefitRuleError('Профиль относится к другому сезону', status_code=400)


async def _check_programs(session, *, university_id, program_ids) -> list[uuid_mod.UUID]:
    """Все программы существуют и принадлежат этому вузу; дубли схлопываются."""
    unique: list[uuid_mod.UUID] = []
    seen = set()
    for raw in program_ids or []:
        value = _as_uuid(raw)
        if value not in seen:
            seen.add(value)
            unique.append(value)
    if not unique:
        return []
    found = set(
        (
            await session.execute(
                select(UniversityProgram.id).where(
                    UniversityProgram.id.in_(unique),
                    UniversityProgram.university_id == university_id,
                )
            )
        ).scalars().all()
    )
    missing = [item for item in unique if item not in found]
    if missing:
        raise BenefitRuleError(
            'Программа не найдена у этого университета: ' + ', '.join(map(str, missing)),
            status_code=400,
        )
    return unique


async def _current_program_ids(session, rule_id) -> list[uuid_mod.UUID]:
    return list(
        (
            await session.execute(
                select(BenefitRuleProgram.program_id)
                .where(BenefitRuleProgram.rule_id == rule_id)
                .order_by(BenefitRuleProgram.program_id)
            )
        ).scalars().all()
    )


async def _replace_programs(session, rule, program_ids) -> None:
    await session.execute(
        BenefitRuleProgram.__table__.delete().where(BenefitRuleProgram.rule_id == rule.id)
    )
    for program_id in program_ids:
        session.add(
            BenefitRuleProgram(
                rule_id=rule.id, program_id=program_id, university_id=rule.university_id
            )
        )


async def _snapshot(session, rule) -> dict:
    """Полный снимок правила для истории версий (JSON-совместимый).

    Снимок включает идентификаторы и названия программ: откат восстанавливает
    набор по идентификаторам, а названия нужны, чтобы история читалась и после
    переименования программы.
    """
    program_rows = (
        await session.execute(
            select(UniversityProgram.id, UniversityProgram.name)
            .join(BenefitRuleProgram, BenefitRuleProgram.program_id == UniversityProgram.id)
            .where(BenefitRuleProgram.rule_id == rule.id)
            .order_by(UniversityProgram.name_norm)
        )
    ).all()
    return {
        'season_id': str(rule.season_id) if rule.season_id else None,
        'profile_id': str(rule.profile_id) if rule.profile_id else None,
        'benefit_type': rule.benefit_type,
        'result_requirement': rule.result_requirement,
        'subject': rule.subject,
        'extra_requirements': rule.extra_requirements,
        'source_url': rule.source_url,
        'valid_until': _iso(rule.valid_until),
        'source_doc_id': str(rule.source_doc_id) if rule.source_doc_id else None,
        'status': rule.status,
        'verification_status': rule.verification_status,
        'verification_note': rule.verification_note,
        'university_confirmed': bool(rule.university_confirmed),
        'program_ids': [str(program_id) for program_id, _name in program_rows],
        'programs': [name for _program_id, name in program_rows],
    }


async def _record_version(
    session,
    rule,
    *,
    changed_by=None,
    reason: str | None = None,
    is_rollback: bool = False,
) -> int:
    """Записать текущее состояние как новую версию и вернуть её номер.

    Вызывающий держит ``FOR UPDATE`` на строке правила, поэтому две версии с
    одним номером невозможны.
    """
    rule.version = (rule.version or 0) + 1
    session.add(
        BenefitRuleVersion(
            rule_id=rule.id,
            version=rule.version,
            snapshot=await _snapshot(session, rule),
            changed_by=_as_uuid(changed_by) if changed_by else None,
            changed_at=datetime.now(timezone.utc),
            reason=reason,
            verification_status=rule.verification_status,
            source_doc_id=rule.source_doc_id,
            source_meta=rule.source_meta,
            is_rollback=is_rollback,
        )
    )
    return rule.version


def _clear_verification(rule) -> None:
    rule.verification_status = VERIFICATION_UNVERIFIED
    rule.verified_by = None
    rule.verified_at = None
    rule.verification_note = None


def _set_dedup_key(rule, program_ids) -> None:
    rule.dedup_key = build_dedup_key(
        season_id=rule.season_id,
        profile_id=rule.profile_id,
        benefit_type=rule.benefit_type,
        result_requirement=rule.result_requirement,
        subject=rule.subject,
        program_ids=program_ids,
    )


def _duplicate_error() -> BenefitRuleError:
    return BenefitRuleError(
        'Такое правило уже есть: у этого университета и олимпиады уже '
        'записано действующее правило с теми же сезоном, профилем, видом '
        'льготы, результатом, предметом и программами. Измените существующее '
        'правило вместо создания копии.',
        status_code=409,
    )


async def _lock_rule(session, rule_id, university_id=None):
    statement = (
        select(BenefitRule).where(BenefitRule.id == _as_uuid(rule_id)).with_for_update()
    )
    if university_id is not None:
        statement = statement.where(BenefitRule.university_id == _as_uuid(university_id))
    return (await session.execute(statement)).scalar_one_or_none()


def _check_expected_version(rule, expected_version) -> None:
    if expected_version is not None and int(expected_version) != int(rule.version or 0):
        raise BenefitRuleError(
            f'Правило уже изменено (текущая версия {rule.version}, вы правили '
            f'версию {expected_version}). Обновите страницу и повторите правку.',
            status_code=409,
        )


def _parse_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


async def create_rule(
    university_id,
    *,
    data: dict,
    created_by=None,
    admin: bool = False,
    publish: bool = False,
    reason: str | None = None,
) -> dict:
    """Создать правило льготы и записать версию 1.

    ``data``: ``olympiad_id`` (обязательно), ``season_id``, ``profile_id``,
    ``benefit_type``, ``result_requirement``, ``subject``, ``extra_requirements``,
    ``source_url``, ``valid_until``, ``program_ids``, а для администратора ещё
    ``source_doc_id`` и ``verification_status``.
    """
    _validate_enums(data)
    university_uuid = _as_uuid(university_id)
    olympiad_uuid = _as_uuid(data.get('olympiad_id'))
    season_uuid = _as_uuid_or_none(data.get('season_id'))
    profile_uuid = _as_uuid_or_none(data.get('profile_id'))
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        olympiad_status = (
            await session.execute(
                select(Olympiads.status).where(Olympiads.id == olympiad_uuid).with_for_update()
            )
        ).scalar_one_or_none()
        if olympiad_status is None:
            raise BenefitRuleError('Олимпиада не найдена', status_code=404)
        if olympiad_status != OLYMPIAD_ACTIVE_STATUS:
            raise BenefitRuleError(
                'Олимпиада архивирована: её нет в актуальном перечне РСОШ, '
                'новые правила льгот по ней не заводятся. Уже записанные '
                'правила сохраняются как исторические.',
                status_code=409,
            )
        await _check_season_and_profile(
            session, olympiad_id=olympiad_uuid, season_id=season_uuid, profile_id=profile_uuid
        )
        program_ids = await _check_programs(
            session, university_id=university_uuid, program_ids=data.get('program_ids')
        )
        source_doc_id = _as_uuid_or_none(data.get('source_doc_id')) if admin else None
        if source_doc_id is not None:
            doc_exists = (
                await session.execute(select(Docs.id).where(Docs.id == source_doc_id))
            ).scalar_one_or_none()
            if doc_exists is None:
                raise BenefitRuleError('Документ не найден', status_code=404)

        rule = BenefitRule(
            university_id=university_uuid,
            olympiad_id=olympiad_uuid,
            season_id=season_uuid,
            profile_id=profile_uuid,
            status=RULE_STATUS_PUBLISHED if publish else RULE_STATUS_DRAFT,
            createdBy=_as_uuid(created_by) if created_by else None,
            published_by=_as_uuid(created_by) if publish and created_by else None,
            published_at=now if publish else None,
            source_doc_id=source_doc_id,
            benefit_type=data.get('benefit_type') or 'BVI',
            result_requirement=_clean(data.get('result_requirement')),
            subject=_clean(data.get('subject')),
            extra_requirements=_clean(data.get('extra_requirements')),
            source_url=_clean(data.get('source_url')),
            valid_until=_parse_date(data.get('valid_until')),
            verification_status=VERIFICATION_UNVERIFIED,
            version=0,
            createdAt=now,
            updatedAt=now,
        )
        _set_dedup_key(rule, program_ids)
        session.add(rule)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise _duplicate_error() from exc
        await _replace_programs(session, rule, program_ids)

        if admin and data.get('verification_status') == VERIFICATION_VERIFIED:
            _require_verifiable(rule)
            rule.verification_status = VERIFICATION_VERIFIED
            rule.verified_by = _as_uuid(created_by) if created_by else None
            rule.verified_at = now
        await _record_version(session, rule, changed_by=created_by, reason=reason)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise _duplicate_error() from exc
        rule_id = rule.id
    return await get_rule(rule_id)


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_verifiable(rule) -> None:
    """``verified`` возможен только с документом и ссылкой на источник (ТЗ §9)."""
    missing = []
    if not rule.source_doc_id:
        missing.append('официальный документ')
    if not rule.source_url:
        missing.append('ссылка на источник')
    if missing:
        raise BenefitRuleError(
            'Нельзя отметить правило как проверенное: не хватает — '
            + ', '.join(missing)
            + '. Подтверждение Papaya требует и документа, и ссылки на оригинал.',
            status_code=409,
        )


async def update_rule(
    rule_id,
    *,
    university_id=None,
    updates: dict,
    changed_by=None,
    admin: bool = False,
    reason: str | None = None,
    expected_version: int | None = None,
) -> dict | None:
    """Изменить правило и записать версию.

    Содержательные изменения сбрасывают проверку Papaya в ``unverified`` —
    кроме случая, когда администратор в этом же запросе явно передал
    ``verification_status``. Представитель менять ``verification_status`` и
    ``source_doc_id`` напрямую не может (документ он загружает отдельным
    маршрутом). Возвращает ``None``, если правила нет.
    """
    allowed = set(CONTENT_FIELDS) | {'program_ids', 'verification_status', 'verification_note'}
    unknown = set(updates) - allowed
    if unknown:
        raise BenefitRuleError(
            f'Неизвестные поля правила: {", ".join(sorted(unknown))}', status_code=400
        )
    if not admin:
        for field in ('verification_status', 'verification_note', 'source_doc_id'):
            updates.pop(field, None)
    _validate_enums(updates)

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id, university_id)
        if rule is None:
            return None
        _check_expected_version(rule, expected_version)
        if rule.status == RULE_STATUS_ARCHIVED:
            raise BenefitRuleError(
                'Архивное правило не редактируется: создайте новое правило или '
                'восстановите это из архива.',
                status_code=409,
            )

        changed_fields: list[str] = []
        season_id = (
            _as_uuid_or_none(updates['season_id']) if 'season_id' in updates else rule.season_id
        )
        profile_id = (
            _as_uuid_or_none(updates['profile_id'])
            if 'profile_id' in updates
            else rule.profile_id
        )
        if 'season_id' in updates and 'profile_id' not in updates and season_id != rule.season_id:
            # Смена сезона без явного профиля: старый профиль заведомо чужой.
            profile_id = None
        await _check_season_and_profile(
            session, olympiad_id=rule.olympiad_id, season_id=season_id, profile_id=profile_id
        )
        if season_id != rule.season_id:
            rule.season_id = season_id
            changed_fields.append('season_id')
        if profile_id != rule.profile_id:
            rule.profile_id = profile_id
            changed_fields.append('profile_id')

        for field in ('benefit_type', 'result_requirement', 'subject', 'extra_requirements', 'source_url'):
            if field in updates:
                value = _clean(updates[field]) if field != 'benefit_type' else updates[field]
                if getattr(rule, field) != value:
                    setattr(rule, field, value)
                    changed_fields.append(field)
        if 'valid_until' in updates:
            value = _parse_date(updates['valid_until'])
            if rule.valid_until != value:
                rule.valid_until = value
                changed_fields.append('valid_until')
        if 'source_doc_id' in updates:
            value = _as_uuid_or_none(updates['source_doc_id'])
            if value is not None:
                doc_exists = (
                    await session.execute(select(Docs.id).where(Docs.id == value))
                ).scalar_one_or_none()
                if doc_exists is None:
                    raise BenefitRuleError('Документ не найден', status_code=404)
            if rule.source_doc_id != value:
                rule.source_doc_id = value
                changed_fields.append('source_doc_id')

        program_ids = await _current_program_ids(session, rule.id)
        if 'program_ids' in updates and updates['program_ids'] is not None:
            new_programs = await _check_programs(
                session, university_id=rule.university_id, program_ids=updates['program_ids']
            )
            if sorted(new_programs) != sorted(program_ids):
                await _replace_programs(session, rule, new_programs)
                program_ids = new_programs
                changed_fields.append('programs')

        verification_changed = False
        if admin and 'verification_status' in updates:
            target = updates['verification_status']
            if target == VERIFICATION_VERIFIED:
                _require_verifiable(rule)
                rule.verification_status = VERIFICATION_VERIFIED
                rule.verified_by = _as_uuid(changed_by) if changed_by else None
                rule.verified_at = now
                rule.verification_note = _clean(updates.get('verification_note'))
            else:
                if target == VERIFICATION_REJECTED and not _clean(updates.get('verification_note')):
                    raise BenefitRuleError(
                        'Укажите причину отклонения: без неё представитель не '
                        'поймёт, что исправить.',
                        status_code=400,
                    )
                rule.verification_status = target
                rule.verified_by = None
                rule.verified_at = None
                rule.verification_note = _clean(updates.get('verification_note'))
            verification_changed = True
        elif changed_fields:
            # Содержание изменилось — прежняя проверка больше ничего не
            # подтверждает.
            if rule.verification_status != VERIFICATION_UNVERIFIED:
                verification_changed = True
            _clear_verification(rule)

        if not changed_fields and not verification_changed:
            return {**(await _reload(session, rule.id)), 'changed': False}

        _set_dedup_key(rule, program_ids)
        rule.updatedAt = now
        await _record_version(session, rule, changed_by=changed_by, reason=reason)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise _duplicate_error() from exc
        rule_id = rule.id
    return {**(await get_rule(rule_id)), 'changed': True}


async def _reload(session, rule_id) -> dict:
    items = await _fetch_enriched(
        session, _enriched_select().where(BenefitRule.id == rule_id)
    )
    return items[0]


async def set_rule_status(
    rule_id,
    *,
    university_id=None,
    status: str,
    changed_by=None,
    reason: str | None = None,
    expected_version: int | None = None,
) -> dict | None:
    """Опубликовать, вернуть в черновик или архивировать правило.

    Публикация делает правило видимым сразу (с пометкой «Не проверено Papaya»,
    пока его не проверил администратор). Архив — обратимое действие: архивное
    правило можно вернуть в черновик, если его содержимое не дублирует другое
    действующее правило.
    """
    if status not in RULE_STATUSES:
        raise BenefitRuleError(
            'Недопустимое состояние. Разрешены: ' + ', '.join(RULE_STATUSES) + '.',
            status_code=400,
        )
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id, university_id)
        if rule is None:
            return None
        _check_expected_version(rule, expected_version)
        if rule.status == status:
            return {**(await _reload(session, rule.id)), 'changed': False}
        if status == RULE_STATUS_PUBLISHED:
            olympiad_status = (
                await session.execute(
                    select(Olympiads.status).where(Olympiads.id == rule.olympiad_id)
                )
            ).scalar_one()
            if olympiad_status != OLYMPIAD_ACTIVE_STATUS:
                raise BenefitRuleError(
                    'Олимпиада архивирована: правило по ней нельзя опубликовать '
                    'как действующее.',
                    status_code=409,
                )
            rule.published_by = _as_uuid(changed_by) if changed_by else None
            rule.published_at = now
        rule.status = status
        rule.updatedAt = now
        await _record_version(session, rule, changed_by=changed_by, reason=reason)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise _duplicate_error() from exc
        rule_id = rule.id
    return {**(await get_rule(rule_id)), 'changed': True}


async def delete_rule(rule_id, *, university_id=None) -> bool:
    """Физически удалить черновик. Опубликованное/архивное — только архив.

    Возвращает ``False``, если правила нет.
    """
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id, university_id)
        if rule is None:
            return False
        if rule.status != RULE_STATUS_DRAFT:
            raise BenefitRuleError(
                'Удалить можно только черновик. Опубликованное правило '
                'переводится в архив, чтобы сохранить историю.',
                status_code=409,
            )
        await session.delete(rule)
        await session.commit()
        return True


async def set_verification(
    rule_id,
    *,
    status: str,
    note: str | None = None,
    admin_id=None,
    expected_version: int | None = None,
) -> dict | None:
    """Проверка Papaya: ``verified`` / ``rejected`` / ``unverified``.

    ``verified`` требует документа и ссылки на источник; ``rejected`` — причину.
    Решение записывается как версия: в истории видно, кто и когда проверил.
    """
    if status not in VERIFICATION_STATUSES:
        raise BenefitRuleError(
            'Недопустимый статус проверки. Разрешены: '
            + ', '.join(VERIFICATION_STATUSES)
            + '.',
            status_code=400,
        )
    note = _clean(note)
    if status == VERIFICATION_REJECTED and not note:
        raise BenefitRuleError(
            'Укажите причину отклонения: без неё представитель не поймёт, что исправить.',
            status_code=400,
        )
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id)
        if rule is None:
            return None
        _check_expected_version(rule, expected_version)
        if status == VERIFICATION_VERIFIED:
            _require_verifiable(rule)
            rule.verified_by = _as_uuid(admin_id) if admin_id else None
            rule.verified_at = now
        else:
            rule.verified_by = None
            rule.verified_at = None
        rule.verification_status = status
        rule.verification_note = note
        rule.updatedAt = now
        await _record_version(
            session,
            rule,
            changed_by=admin_id,
            reason=note or {'verified': 'Проверено Papaya', 'unverified': 'Проверка снята'}.get(status),
        )
        await session.commit()
        rule_id = rule.id
    return await get_rule(rule_id)


async def attach_document(
    rule_id,
    *,
    university_id=None,
    doc_id,
    changed_by=None,
    reason: str | None = None,
) -> dict | None:
    """Привязать загруженный официальный документ к правилу (новая версия).

    Смена документа — содержательное изменение: прежняя проверка снимается.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id, university_id)
        if rule is None:
            return None
        rule.source_doc_id = _as_uuid(doc_id)
        _clear_verification(rule)
        rule.updatedAt = now
        await _record_version(
            session, rule, changed_by=changed_by, reason=reason or 'Загружен документ'
        )
        await session.commit()
        rule_id = rule.id
    return await get_rule(rule_id)


async def list_versions(rule_id) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitRuleVersion)
            .where(BenefitRuleVersion.rule_id == _as_uuid(rule_id))
            .order_by(BenefitRuleVersion.version)
        )
        return [benefit_version_to_dict(row) for row in result.scalars().all()]


async def rollback_rule(
    rule_id,
    *,
    university_id=None,
    version: int,
    changed_by=None,
    reason: str | None = None,
    expected_version: int | None = None,
) -> dict | None:
    """Восстановить содержимое выбранной версии новой версией (``is_rollback``).

    Восстанавливаются содержательные поля и набор программ. Проверка Papaya
    **не** восстанавливается: восстановленное правило всегда ``unverified``,
    пока его не проверят заново. Публикационное состояние не меняется.
    Возвращает ``None``, если правила или версии нет.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id, university_id)
        if rule is None:
            return None
        _check_expected_version(rule, expected_version)
        source = (
            await session.execute(
                select(BenefitRuleVersion).where(
                    BenefitRuleVersion.rule_id == rule.id,
                    BenefitRuleVersion.version == int(version),
                )
            )
        ).scalar_one_or_none()
        if source is None:
            return None
        snapshot = source.snapshot or {}

        season_id = _as_uuid_or_none(snapshot.get('season_id'))
        profile_id = _as_uuid_or_none(snapshot.get('profile_id'))
        try:
            await _check_season_and_profile(
                session, olympiad_id=rule.olympiad_id, season_id=season_id, profile_id=profile_id
            )
        except BenefitRuleError:
            # Сезон/профиль из старой версии уже удалён: восстанавливаем без них.
            season_id, profile_id = None, None
        rule.season_id = season_id
        rule.profile_id = profile_id
        rule.benefit_type = snapshot.get('benefit_type') or rule.benefit_type
        rule.result_requirement = snapshot.get('result_requirement')
        rule.subject = snapshot.get('subject')
        rule.extra_requirements = snapshot.get('extra_requirements')
        rule.source_url = snapshot.get('source_url')
        rule.valid_until = _parse_date(snapshot.get('valid_until'))
        doc_id = _as_uuid_or_none(snapshot.get('source_doc_id'))
        if doc_id is not None:
            doc_exists = (
                await session.execute(select(Docs.id).where(Docs.id == doc_id))
            ).scalar_one_or_none()
            if doc_exists is None:
                doc_id = None
        rule.source_doc_id = doc_id

        wanted = [_as_uuid(item) for item in snapshot.get('program_ids') or []]
        existing: set = set()
        if wanted:
            existing = set(
                (
                    await session.execute(
                        select(UniversityProgram.id).where(
                            UniversityProgram.id.in_(wanted),
                            UniversityProgram.university_id == rule.university_id,
                        )
                    )
                ).scalars().all()
            )
        # Программа из старой версии могла быть удалена — она просто выпадает.
        program_ids = [item for item in wanted if item in existing]
        await _replace_programs(session, rule, program_ids)

        _clear_verification(rule)
        _set_dedup_key(rule, program_ids)
        rule.updatedAt = now
        await _record_version(
            session,
            rule,
            changed_by=changed_by,
            reason=reason or f'Откат к версии {version}',
            is_rollback=True,
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise BenefitRuleError(
                'Откат невозможен: восстановленное содержимое совпадает с другим '
                'действующим правилом этого вуза и олимпиады.',
                status_code=409,
            ) from exc
        rule_id = rule.id
    return await get_rule(rule_id)


async def set_university_confirmation(
    rule_id,
    *,
    university_id=None,
    confirmed: bool,
    changed_by=None,
) -> dict | None:
    """Отметка «подтверждено вузом» — независимо от проверки Papaya."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rule = await _lock_rule(session, rule_id, university_id)
        if rule is None:
            return None
        if bool(rule.university_confirmed) == bool(confirmed):
            return await _reload(session, rule.id)
        rule.university_confirmed = bool(confirmed)
        rule.university_confirmed_at = now if confirmed else None
        rule.updatedAt = now
        await _record_version(
            session,
            rule,
            changed_by=changed_by,
            reason='Подтверждено вузом' if confirmed else 'Подтверждение вуза снято',
        )
        await session.commit()
        rule_id = rule.id
    return await get_rule(rule_id)
