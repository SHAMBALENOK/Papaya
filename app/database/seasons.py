"""Слой доступа к сезонам и профилям сезонов.

Сезон — только олимпиада и метка года. Профиль — название и уровень РСОШ,
причём уровень принадлежит профилю конкретного сезона и не наследуется.
"""

import uuid as uuid_mod

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.models.benefits import BenefitRule
from app.models.seasons import RSOSH_LEVELS, OlympiadSeason, SeasonProfile


class VersionConflict(Exception):
    """Сезон или профиль изменился между чтением и записью."""


class SeasonConflict(ValueError):
    """Сезон нельзя создать или удалить: дубль или связанные правила."""


def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _iso(v):
    return v.isoformat() if v else None


def normalize_level(value):
    if value is None or value == '':
        return None
    v = str(value).strip()
    if v not in RSOSH_LEVELS:
        raise SeasonConflict('rsosh_level must be 1, 2, 3 or empty')
    return v


def season_to_dict(s):
    return {
        'id': str(s.id),
        'olympiad_id': str(s.olympiad_id),
        'season_label': s.season_label,
        'version': int(getattr(s, 'version', 1) or 1),
        'is_archived': bool(getattr(s, 'is_archived', False)),
        'createdAt': _iso(s.createdAt),
        'updatedAt': _iso(s.updatedAt),
    }


def profile_to_dict(p):
    return {
        'id': str(p.id),
        'season_id': str(p.season_id),
        'name': p.name,
        'rsosh_level': p.rsosh_level,
        'description': p.description,
        'version': int(getattr(p, 'version', 1) or 1),
        'createdAt': _iso(p.createdAt),
        'updatedAt': _iso(p.updatedAt),
    }


async def list_seasons(olympiad_id, *, include_archived=False):
    async with AsyncSessionLocal() as session:
        stmt = select(OlympiadSeason).where(
            OlympiadSeason.olympiad_id == _as_uuid(olympiad_id)
        )
        if not include_archived:
            stmt = stmt.where(OlympiadSeason.is_archived.is_(False))
        result = await session.execute(
            stmt.order_by(OlympiadSeason.season_label.desc(), OlympiadSeason.id)
        )
        return [season_to_dict(x) for x in result.scalars().all()]


async def list_seasons_with_profiles(olympiad_id, *, include_archived=True):
    """Сезоны вместе с профилями: страница олимпиады не делает N+1 запросов."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(OlympiadSeason)
            .where(OlympiadSeason.olympiad_id == _as_uuid(olympiad_id))
            .options(selectinload(OlympiadSeason.profiles))
            .order_by(OlympiadSeason.season_label.desc(), OlympiadSeason.id)
        )
        if not include_archived:
            stmt = stmt.where(OlympiadSeason.is_archived.is_(False))
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                **season_to_dict(s),
                'profiles': [
                    profile_to_dict(p)
                    for p in sorted(
                        s.profiles, key=lambda p: (p.rsosh_level or '9', p.name)
                    )
                ],
            }
            for s in rows
        ]


async def list_all_seasons(*, search=None, include_archived=True, limit=None, offset=0):
    async with AsyncSessionLocal() as session:
        stmt = select(OlympiadSeason)
        count_stmt = select(func.count()).select_from(OlympiadSeason)
        if search:
            pattern = f'%{search.strip()}%'
            stmt = stmt.where(OlympiadSeason.season_label.ilike(pattern))
            count_stmt = count_stmt.where(OlympiadSeason.season_label.ilike(pattern))
        if not include_archived:
            stmt = stmt.where(OlympiadSeason.is_archived.is_(False))
            count_stmt = count_stmt.where(OlympiadSeason.is_archived.is_(False))
        total = int((await session.execute(count_stmt)).scalar_one())
        stmt = stmt.order_by(
            OlympiadSeason.season_label.desc(), OlympiadSeason.id
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(max(0, int(offset or 0)))
        result = await session.execute(stmt)
        return [season_to_dict(x) for x in result.scalars().all()], total


async def archive_season(season_id, archived: bool = True):
    return await update_season(season_id, {'is_archived': bool(archived)})


async def get_season(season_id):
    async with AsyncSessionLocal() as session:
        s = await session.get(OlympiadSeason, _as_uuid(season_id))
        return season_to_dict(s) if s else None


async def create_season(data: dict):
    label = (data.get('season_label') or '').strip()
    if not label:
        raise SeasonConflict('season_label is required')
    async with AsyncSessionLocal() as session:
        s = OlympiadSeason(
            olympiad_id=_as_uuid(data['olympiad_id']),
            season_label=label,
        )
        session.add(s)
        await session.commit()
        await session.refresh(s)
        return season_to_dict(s)


async def update_season(season_id, data: dict, *, expected_version=None):
    """Обновить сезон.

    Версия проверяется под ``FOR UPDATE``: предварительное чтение в роутере
    оставляло окно, в котором параллельная правка проходила обе проверки и
    одна из них молча терялась.
    """
    allowed = {'season_label', 'is_archived'}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OlympiadSeason)
            .where(OlympiadSeason.id == _as_uuid(season_id))
            .with_for_update()
        )
        s = result.scalar_one_or_none()
        if not s:
            return None
        if expected_version is not None and int(expected_version) != int(
            s.version or 1
        ):
            raise VersionConflict('Version conflict')
        for k, v in data.items():
            if k not in allowed:
                continue
            if k == 'season_label':
                v = (v or '').strip()
                if not v:
                    raise SeasonConflict('season_label is required')
            setattr(s, k, v)
        s.version = (s.version or 1) + 1
        await session.commit()
        await session.refresh(s)
        return season_to_dict(s)


async def delete_season(season_id):
    async with AsyncSessionLocal() as session:
        s = await session.get(OlympiadSeason, _as_uuid(season_id))
        if not s:
            return False
        rules = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(BenefitRule)
                    .where(BenefitRule.season_id == s.id)
                )
            ).scalar_one()
        )
        if rules:
            raise SeasonConflict(
                'Season has benefit rules; archive it instead of deleting'
            )
        await session.delete(s)
        await session.commit()
        return True


async def list_profiles(season_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SeasonProfile)
            .where(SeasonProfile.season_id == _as_uuid(season_id))
            .order_by(SeasonProfile.rsosh_level.nulls_last(), SeasonProfile.name)
        )
        return [profile_to_dict(x) for x in result.scalars().all()]


async def get_profile(profile_id):
    async with AsyncSessionLocal() as session:
        p = await session.get(SeasonProfile, _as_uuid(profile_id))
        return profile_to_dict(p) if p else None


async def create_profile(data: dict):
    name = (data.get('name') or '').strip()
    if not name:
        raise SeasonConflict('Profile name is required')
    async with AsyncSessionLocal() as session:
        p = SeasonProfile(
            season_id=_as_uuid(data['season_id']),
            name=name,
            name_norm=normalize_name(name),
            rsosh_level=normalize_level(data.get('rsosh_level')),
            description=(data.get('description') or '').strip() or None,
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return profile_to_dict(p)


async def update_profile(profile_id, data: dict, *, expected_version=None):
    allowed = {'name', 'rsosh_level', 'description'}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SeasonProfile)
            .where(SeasonProfile.id == _as_uuid(profile_id))
            .with_for_update()
        )
        p = result.scalar_one_or_none()
        if not p:
            return None
        if expected_version is not None and int(expected_version) != int(
            p.version or 1
        ):
            raise VersionConflict('Version conflict')
        for k, v in data.items():
            if k not in allowed:
                continue
            if k == 'name':
                v = (v or '').strip()
                if not v:
                    raise SeasonConflict('Profile name is required')
                p.name_norm = normalize_name(v)
            elif k == 'rsosh_level':
                v = normalize_level(v)
            elif k == 'description':
                v = (v or '').strip() or None
            setattr(p, k, v)
        p.version = (p.version or 1) + 1
        await session.commit()
        await session.refresh(p)
        return profile_to_dict(p)


async def delete_profile(profile_id):
    async with AsyncSessionLocal() as session:
        p = await session.get(SeasonProfile, _as_uuid(profile_id))
        if not p:
            return False
        rules = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(BenefitRule)
                    .where(BenefitRule.profile_id == p.id)
                )
            ).scalar_one()
        )
        if rules:
            raise SeasonConflict(
                'Profile has benefit rules; remove the rules first'
            )
        await session.delete(p)
        await session.commit()
        return True
