import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.models.seasons import OlympiadSeason, SeasonProfile

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))

def _iso(v):
    return v.isoformat() if v else None

def season_to_dict(s):
    return {
        'id': str(s.id),
        'olympiad_id': str(s.olympiad_id),
        'season_label': s.season_label,
        'rsosh_level': s.rsosh_level,
        'registration_start': _iso(s.registration_start),
        'registration_end': _iso(s.registration_end),
        'event_start': _iso(s.event_start),
        'event_end': _iso(s.event_end),
        'extra_params': s.extra_params,
        'availability': s.availability,
        'source_doc_id': str(s.source_doc_id) if s.source_doc_id else None,
        'createdAt': _iso(s.createdAt),
        'updatedAt': _iso(s.updatedAt),
    }

def profile_to_dict(p):
    return {
        'id': str(p.id),
        'season_id': str(p.season_id),
        'discipline': p.discipline,
        'subject': p.subject,
        'profile_name': p.profile_name,
        'description': p.description,
        'extra_params': p.extra_params,
        'createdAt': _iso(p.createdAt),
        'updatedAt': _iso(p.updatedAt),
    }

async def list_seasons(olympiad_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OlympiadSeason).where(OlympiadSeason.olympiad_id == _as_uuid(olympiad_id))
        )
        return [season_to_dict(x) for x in result.scalars().all()]

async def get_season(season_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(OlympiadSeason).where(OlympiadSeason.id == _as_uuid(season_id)))
        s = result.scalar_one_or_none()
        return season_to_dict(s) if s else None

async def create_season(data: dict):
    async with AsyncSessionLocal() as session:
        s = OlympiadSeason(**data)
        session.add(s)
        await session.commit()
        await session.refresh(s)
        return season_to_dict(s)

async def update_season(season_id, data: dict):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(OlympiadSeason).where(OlympiadSeason.id == _as_uuid(season_id)))
        s = result.scalar_one_or_none()
        if not s:
            return None
        for k, v in data.items():
            if v is not None or k in data:
                setattr(s, k, v)
        s.version = (s.version or 1) + 1
        await session.commit()
        await session.refresh(s)
        return season_to_dict(s)

async def delete_season(season_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(OlympiadSeason).where(OlympiadSeason.id == _as_uuid(season_id)))
        s = result.scalar_one_or_none()
        if not s:
            return False
        await session.delete(s)
        await session.commit()
        return True

async def list_profiles(season_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SeasonProfile).where(SeasonProfile.season_id == _as_uuid(season_id)))
        return [profile_to_dict(x) for x in result.scalars().all()]

async def create_profile(data: dict):
    async with AsyncSessionLocal() as session:
        p = SeasonProfile(**data)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return profile_to_dict(p)

async def get_profile(profile_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SeasonProfile).where(SeasonProfile.id == _as_uuid(profile_id)))
        p = result.scalar_one_or_none()
        return profile_to_dict(p) if p else None