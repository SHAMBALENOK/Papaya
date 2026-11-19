"""Применение плана импорта перечня РСОШ.

План — это решение администратора, а не данные документа. Применение плана
должно быть атомарным: либо каталог получает весь перечень, либо не меняется
ничего. Поэтому вся запись идёт одной транзакцией под advisory-блокировкой,
общей с прежним импортёром: два одновременных применения не могут создать
две одинаковые олимпиады или два одинаковых сезона.

Повторное применение того же документа запрещено. Это не ограничение ради
ограничения: после применения каталог соответствует перечню, а повторная
запись тех же строк либо создаст дубликаты, либо перезапишет ручные правки.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database.search import normalize_name
from app.models.docs import Docs
from app.models.imports import ImportJob, ImportRecord
from app.models.olympiads import Olympiads
from app.models.seasons import OlympiadSeason, SeasonProfile
from app.rsosh import states
from app.rsosh.persist import ARCHIVE_BY_RSOSH, RSOSH_SNAPSHOT_LOCK_KEY
from app.rsosh.types import RsoshConflictError, RsoshError

logger = logging.getLogger('papaya.rsosh.list_apply')

HISTORY_LIMIT = 1000


class PlanError(RsoshError):
    """План нельзя применить: он неполон или противоречив."""


def _uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _history_entry(doc_id, **values) -> dict:
    return {
        'at': _now(),
        'doc_id': str(doc_id),
        **values,
    }


async def _locked_doc(session, doc_id) -> Docs:
    result = await session.execute(
        select(Docs).where(Docs.id == _uuid(doc_id)).with_for_update()
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise PlanError('Document not found')
    return doc


def _plan_error(plan: dict) -> str | None:
    if not plan:
        return 'План импорта не найден: сначала разберите документ'
    if not plan.get('season_label'):
        return 'В плане не определён учебный год перечня'
    unresolved = [
        item['name']
        for item in plan.get('olympiads') or []
        if (item.get('match') or {}).get('action') == 'review'
    ]
    if unresolved:
        shown = ', '.join(unresolved[:5])
        return (
            'Есть олимпиады, для которых не выбрано существующее совпадение: '
            f'{shown}'
        )
    for item in plan.get('olympiads') or []:
        action = (item.get('match') or {}).get('action')
        if action not in ('create', 'use', 'skip'):
            return f'Неизвестное действие для олимпиады «{item.get("name")}»'
        for profile in item.get('profiles') or []:
            profile_action = (profile.get('match') or {}).get('action')
            if profile_action == 'skip':
                continue
            if profile_action not in ('create', 'use', 'update'):
                return (
                    f'Олимпиада «{item.get("name")}»: неизвестное действие '
                    f'для профиля «{profile.get("name")}»'
                )
            if not profile.get('name'):
                return (
                    f'Олимпиада «{item.get("name")}»: у профиля пустое '
                    'название'
                )
            if profile_action == 'create' and not profile.get('level'):
                return (
                    f'Олимпиада «{item.get("name")}»: у нового профиля '
                    f'«{profile.get("name")}» не указан уровень'
                )
    return None


async def apply_plan(
    doc_id,
    *,
    user_id=None,
    mark_missing: bool = False,
    job_id=None,
) -> dict:
    """Применить утверждённый план одной транзакцией."""
    from app.database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text('SELECT pg_advisory_xact_lock(:key)'),
                {'key': RSOSH_SNAPSHOT_LOCK_KEY},
            )
            doc_row = await _locked_doc(session, doc_id)
            document = {
                'id': str(doc_row.id),
                'metadata': doc_row.meta or {},
                'status': doc_row.status,
            }
            section = states.rsosh_section(document)
            if section.get('applied_at') or section.get('state') == 'approved':
                raise RsoshConflictError(
                    'Импорт этого документа уже применён: повторное '
                    'применение создало бы дубликаты'
                )
            plan = section.get('plan')
            problem = _plan_error(plan)
            if problem:
                raise PlanError(problem)

            season_label = plan['season_label']
            errors: list[str] = []
            history: list[dict] = []
            records: list[dict] = []
            created_olympiads = 0
            used_olympiads = 0
            restored_olympiads = 0
            created_seasons = 0
            created_profiles = 0
            updated_profiles = 0
            marked_missing: list[str] = []
            missing_profiles: list[str] = []

            for item in plan.get('olympiads') or []:
                match = item.get('match') or {}
                action = match.get('action')
                if action == 'skip':
                    records.append({
                        'name': item.get('name'),
                        'action': 'skip',
                        'status': 'skipped',
                    })
                    continue

                name = (item.get('name') or '').strip()
                name_norm = normalize_name(name)
                if not name_norm:
                    raise PlanError(
                        f'Олимпиада без названия (строка {item.get("number")})'
                    )

                olympiad = None
                if action == 'use':
                    olympiad_id = match.get('olympiad_id')
                    if not olympiad_id:
                        raise PlanError(
                            f'Для олимпиады «{name}» не выбрана запись каталога'
                        )
                    olympiad = await session.get(Olympiads, _uuid(olympiad_id))
                    if olympiad is None:
                        raise PlanError(
                            f'Олимпиада «{name}» не найдена в каталоге'
                        )
                else:
                    existing = (
                        await session.execute(
                            select(Olympiads).where(
                                Olympiads.name_norm == name_norm
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        olympiad = existing
                        action = 'use'

                if olympiad is None:
                    olympiad = Olympiads(
                        name=name,
                        name_norm=name_norm,
                        organizer=(item.get('organizer') or '').strip() or None,
                        source_doc_id=_uuid(doc_id),
                        status='PUBLISHED',
                    )
                    session.add(olympiad)
                    await session.flush()
                    created_olympiads += 1
                    records.append({
                        'name': name,
                        'action': 'create',
                        'status': 'created',
                    })
                    history.append(_history_entry(
                        doc_id,
                        action='olympiad_created',
                        olympiad_id=str(olympiad.id),
                        name=name,
                        season=season_label,
                    ))
                else:
                    used_olympiads += 1
                    if olympiad.status == 'ARCHIVED':
                        olympiad.status = 'PUBLISHED'
                        olympiad.archive_reason = None
                        restored_olympiads += 1
                        history.append(_history_entry(
                            doc_id,
                            action='olympiad_restored',
                            olympiad_id=str(olympiad.id),
                            name=olympiad.name,
                            season=season_label,
                        ))
                    if action == 'use' and olympiad.name_norm != name_norm:
                        # Администратор исправил название в плане: каталог
                        # получает новое написание, если оно не занято.
                        clash = (
                            await session.execute(
                                select(Olympiads).where(
                                    Olympiads.name_norm == name_norm,
                                    Olympiads.id != olympiad.id,
                                )
                            )
                        ).scalar_one_or_none()
                        if clash is not None:
                            raise PlanError(
                                f'Название «{name}» уже занято другой '
                                'олимпиадой'
                            )
                        history.append(_history_entry(
                            doc_id,
                            action='olympiad_renamed',
                            olympiad_id=str(olympiad.id),
                            name=olympiad.name,
                            new_name=name,
                            season=season_label,
                        ))
                        olympiad.name = name
                        olympiad.name_norm = name_norm
                    organizer = (item.get('organizer') or '').strip()
                    if organizer and organizer != (olympiad.organizer or ''):
                        olympiad.organizer = organizer
                    records.append({
                        'name': olympiad.name,
                        'action': 'merge',
                        'status': 'updated',
                    })

                season = (
                    await session.execute(
                        select(OlympiadSeason)
                        .where(
                            OlympiadSeason.olympiad_id == olympiad.id,
                            OlympiadSeason.season_label == season_label,
                        )
                        .options(selectinload(OlympiadSeason.profiles))
                    )
                ).scalar_one_or_none()
                existing_profiles: dict[str, SeasonProfile] | None = None
                if season is None:
                    season = OlympiadSeason(
                        olympiad_id=olympiad.id,
                        season_label=season_label,
                    )
                    session.add(season)
                    await session.flush()
                    # У нового сезона профилей заведомо нет. Обращение к
                    # ``season.profiles`` после flush вызвало бы ленивую
                    # загрузку в async-сессии (MissingGreenlet).
                    existing_profiles = {}
                    created_seasons += 1
                    history.append(_history_entry(
                        doc_id,
                        action='season_created',
                        olympiad_id=str(olympiad.id),
                        name=olympiad.name,
                        season=season_label,
                    ))
                elif season.is_archived:
                    season.is_archived = False
                    history.append(_history_entry(
                        doc_id,
                        action='season_restored',
                        olympiad_id=str(olympiad.id),
                        name=olympiad.name,
                        season=season_label,
                    ))

                if existing_profiles is None:
                    existing_profiles = {
                        profile.name_norm: profile for profile in season.profiles
                    }
                seen_profiles: set[str] = set()
                for profile in item.get('profiles') or []:
                    profile_match = profile.get('match') or {}
                    profile_action = profile_match.get('action')
                    if profile_action == 'skip':
                        records.append({
                            'name': profile.get('name'),
                            'action': 'skip',
                            'status': 'skipped',
                        })
                        continue
                    profile_name = (profile.get('name') or '').strip()
                    profile_norm = normalize_name(profile_name)
                    if not profile_norm:
                        errors.append(
                            f'Олимпиада «{olympiad.name}»: профиль без названия'
                        )
                        continue
                    seen_profiles.add(profile_norm)
                    level = profile.get('level')
                    level = str(level).strip() if level else None
                    if level not in (None, '1', '2', '3'):
                        errors.append(
                            f'Олимпиада «{olympiad.name}»: недопустимый уровень '
                            f'«{level}» у профиля «{profile_name}»'
                        )
                        continue

                    existing = existing_profiles.get(profile_norm)
                    if existing is None:
                        if not level:
                            errors.append(
                                f'Олимпиада «{olympiad.name}»: у нового профиля '
                                f'«{profile_name}» не указан уровень'
                            )
                            continue
                        existing = SeasonProfile(
                            season_id=season.id,
                            name=profile_name,
                            name_norm=profile_norm,
                            rsosh_level=level,
                        )
                        session.add(existing)
                        await session.flush()
                        existing_profiles[profile_norm] = existing
                        created_profiles += 1
                        history.append(_history_entry(
                            doc_id,
                            action='profile_created',
                            olympiad_id=str(olympiad.id),
                            name=olympiad.name,
                            season=season_label,
                            profile=profile_name,
                            level=level,
                        ))
                        records.append({
                            'name': f'{olympiad.name}: {profile_name}',
                            'action': 'create',
                            'status': 'created',
                        })
                        continue

                    changed = False
                    if profile_name and profile_name != existing.name:
                        clash = any(
                            other.name_norm == profile_norm
                            and other.id != existing.id
                            for other in existing_profiles.values()
                        )
                        if not clash:
                            existing.name = profile_name
                            changed = True
                    if level and level != existing.rsosh_level:
                        previous = existing.rsosh_level
                        existing.rsosh_level = level
                        changed = True
                        history.append(_history_entry(
                            doc_id,
                            action='profile_level_changed',
                            olympiad_id=str(olympiad.id),
                            name=olympiad.name,
                            season=season_label,
                            profile=existing.name,
                            previous_level=previous,
                            level=level,
                        ))
                    if changed:
                        updated_profiles += 1
                        records.append({
                            'name': f'{olympiad.name}: {existing.name}',
                            'action': 'merge',
                            'status': 'updated',
                        })

                # Профили сезона, которых нет в перечне. Это не удаление:
                # уровень снимается (NULL = профиль не входит в перечень).
                for profile_norm, existing in existing_profiles.items():
                    if profile_norm in seen_profiles:
                        continue
                    if existing.rsosh_level is None:
                        continue
                    label = f'{olympiad.name}: {existing.name}'
                    if not mark_missing:
                        missing_profiles.append(label)
                        continue
                    previous = existing.rsosh_level
                    existing.rsosh_level = None
                    history.append(_history_entry(
                        doc_id,
                        action='profile_absent',
                        olympiad_id=str(olympiad.id),
                        name=olympiad.name,
                        season=season_label,
                        profile=existing.name,
                        previous_level=previous,
                    ))
                    marked_missing.append(label)

            # Олимпиады каталога, которых нет в перечне. Архивируются только
            # по полному перечню и только по решению администратора.
            if mark_missing and plan.get('missing_allowed'):
                for item in plan.get('missing') or []:
                    olympiad = await session.get(
                        Olympiads, _uuid(item['olympiad_id'])
                    )
                    if olympiad is None or olympiad.status == 'ARCHIVED':
                        continue
                    olympiad.status = 'ARCHIVED'
                    olympiad.archive_reason = ARCHIVE_BY_RSOSH
                    marked_missing.append(olympiad.name)
                    history.append(_history_entry(
                        doc_id,
                        action='olympiad_absent',
                        olympiad_id=str(olympiad.id),
                        name=olympiad.name,
                        season=season_label,
                    ))

            if errors:
                # Ни одна ошибка строки не должна попасть в каталог: план
                # проверяется до транзакции, но правки администратора могли
                # сделать строку неполной уже после проверки.
                raise PlanError('; '.join(errors))

            summary = {
                'created': created_olympiads,
                'used': used_olympiads,
                'restored': restored_olympiads,
                'seasons_created': created_seasons,
                'profiles_created': created_profiles,
                'profiles_updated': updated_profiles,
                'absent': marked_missing,
                'errors': errors,
            }

            doc_row.status = states.DOCS_STATUS['approved']
            doc_row.meta = states.docs_metadata_with_section(
                {'metadata': doc_row.meta},
                {
                    **section,
                    'state': 'approved',
                    'finished_at': _now(),
                    'applied_at': _now(),
                    'confirm': summary,
                    'history': (list(section.get('history') or []) + history)[
                        -HISTORY_LIMIT:
                    ],
                },
            )
            doc_row.updatedAt = datetime.now(timezone.utc)

            job = None
            if job_id:
                job = await session.get(ImportJob, _uuid(job_id))
            if job is None:
                # Прогон уже создан маршрутом старта импорта: применять план
                # нужно в него же, иначе в истории остался бы вечный
                # PROCESSING и отдельная запись об успехе.
                job = (
                    await session.execute(
                        select(ImportJob)
                        .where(
                            ImportJob.doc_id == doc_row.id,
                            ImportJob.status == 'PROCESSING',
                        )
                        .order_by(ImportJob.started_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if job is None:
                job = ImportJob(
                    doc_id=doc_row.id,
                    kind='RSOSH',
                    status='APPLIED',
                    started_by=_uuid(user_id) if user_id else None,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    summary=summary,
                )
                session.add(job)
            else:
                job.status = 'APPLIED'
                job.finished_at = datetime.now(timezone.utc)
                job.summary = summary
            await session.flush()
            for record in records:
                session.add(
                    ImportRecord(
                        job_id=job.id,
                        name=record.get('name'),
                        action=record.get('action'),
                        status=record.get('status'),
                        payload=record,
                    )
                )

            await session.commit()
            return {
                'result': summary,
                'records': records,
                'history': history,
                'missing_profiles': missing_profiles,
                'marked_absent': marked_missing,
                'errors': errors,
            }
        except (PlanError, RsoshConflictError):
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            logger.exception('rsosh: applying list plan failed')
            raise
