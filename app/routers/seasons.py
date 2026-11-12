import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import database
from app.core import deps

seasons_page = APIRouter(prefix='/seasons', tags=['seasons'])
olympiad_seasons_page = APIRouter(tags=['seasons'])

logger = logging.getLogger('papaya.seasons')


class SeasonCreate(BaseModel):
    version: int | None = None
    season_label: str
    rsosh_level: str | None = None
    registration_start: str | None = None
    registration_end: str | None = None
    event_start: str | None = None
    event_end: str | None = None
    extra_params: dict | None = None
    availability: str | None = None
    source_doc_id: str | None = None


class ProfileCreate(BaseModel):
    discipline: str | None = None
    subject: str | None = None
    profile_name: str | None = None
    description: str | None = None
    extra_params: dict | None = None


def _parse_dt(v):
    if not v:
        return None
    from datetime import datetime
    # Клиент присылает ISO из toISOString(): с суффиксом Z. fromisoformat
    # понимает его не во всех поддерживаемых версиях Python.
    return datetime.fromisoformat(str(v).replace('Z', '+00:00'))


@olympiad_seasons_page.get('/olympiads/{olympiad_id}/seasons')
async def list_olympiad_seasons(olympiad_id: uuid.UUID):
    try:
        seasons = await database.seasons.list_seasons(olympiad_id)
        return {'seasons': seasons}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiad_seasons_page.post('/olympiads/{olympiad_id}/seasons')
async def create_olympiad_season(olympiad_id: uuid.UUID, body: SeasonCreate, current_user: dict = Depends(deps.require_admin)):
    try:
        # Проверяем олимпиаду заранее: иначе нарушение внешнего ключа
        # неотличимо от дубля сезона и клиент получал бы 409 «сезон уже есть»
        # вместо честного 404.
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        data = body.model_dump()
        data['olympiad_id'] = str(olympiad_id)
        for f in ('registration_start', 'registration_end', 'event_start', 'event_end'):
            data[f] = _parse_dt(data[f])
        season = await database.seasons.create_season(data)
        await database.audit.log_action('olympiad_season', season['id'], 'create', user_id=current_user['id'], after=season)
        return season
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail='Season with this label already exists for the olympiad',
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.get('/{season_id}')
async def get_season(season_id: uuid.UUID):
    try:
        season = await database.seasons.get_season(season_id)
        if not season:
            raise HTTPException(status_code=404, detail='Season not found')
        return season
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.put('/{season_id}')
async def update_season(season_id: uuid.UUID, body: SeasonCreate, current_user: dict = Depends(deps.require_admin)):
    try:
        existing = await database.seasons.get_season(season_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Season not found')
        if body.version is not None and int(body.version) != int(existing.get('version', 0)):
            raise HTTPException(status_code=409, detail='Version conflict')
        data = body.model_dump(exclude_unset=True)
        data.pop('version', None)
        for f in ('registration_start', 'registration_end', 'event_start', 'event_end'):
            if f in data:
                data[f] = _parse_dt(data[f])
        season = await database.seasons.update_season(season_id, data)
        if not season:
            raise HTTPException(status_code=404, detail='Season not found')
        await database.audit.log_action('olympiad_season', season_id, 'update', user_id=current_user['id'], after=season)
        return season
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail='Season with this label already exists for the olympiad',
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.get('/{season_id}/profiles')
async def list_season_profiles(season_id: uuid.UUID):
    try:
        profiles = await database.seasons.list_profiles(season_id)
        return {'profiles': profiles}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.post('/{season_id}/profiles')
async def create_season_profile(season_id: uuid.UUID, body: ProfileCreate, current_user: dict = Depends(deps.require_admin)):
    try:
        data = body.model_dump()
        data['season_id'] = str(season_id)
        profile = await database.seasons.create_profile(data)
        return profile
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')