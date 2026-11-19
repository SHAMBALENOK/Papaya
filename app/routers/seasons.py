"""API сезонов и профилей сезонов.

Сезон — это олимпиада и метка года. Дат регистрации/проведения и флага
доступности в контракте нет: Papaya их не хранит. Профиль сезона — название и
уровень РСОШ (1, 2, 3 или пусто), причём уровень принадлежит конкретному
профилю конкретного сезона.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError

from app import database
from app.core import deps
from app.models.seasons import RSOSH_LEVELS

seasons_page = APIRouter(prefix='/seasons', tags=['seasons'])
olympiad_seasons_page = APIRouter(tags=['seasons'])
profiles_page = APIRouter(prefix='/profiles', tags=['seasons'])

logger = logging.getLogger('papaya.seasons')


class SeasonCreate(BaseModel):
    season_label: str

    @field_validator('season_label')
    @classmethod
    def _check_label(cls, v):
        try:
            return database.seasons.validate_season_label(v)
        except database.seasons.SeasonConflict as exc:
            raise ValueError(str(exc)) from exc


class SeasonUpdate(BaseModel):
    version: int | None = None
    season_label: str | None = None
    is_archived: bool | None = None

    @field_validator('season_label')
    @classmethod
    def _check_label(cls, v):
        if v is None:
            return v
        try:
            return database.seasons.validate_season_label(v)
        except database.seasons.SeasonConflict as exc:
            raise ValueError(str(exc)) from exc


class ProfileCreate(BaseModel):
    name: str
    rsosh_level: str | None = None
    description: str | None = None

    @field_validator('name')
    @classmethod
    def _check_name(cls, v):
        v = (v or '').strip()
        if not v:
            raise ValueError('name is required')
        return v

    @field_validator('rsosh_level')
    @classmethod
    def _check_level(cls, v):
        if v is None or v == '':
            return None
        v = str(v).strip()
        if v not in RSOSH_LEVELS:
            raise ValueError('rsosh_level must be 1, 2, 3 or empty')
        return v


class ProfileUpdate(BaseModel):
    version: int | None = None
    name: str | None = None
    rsosh_level: str | None = None
    description: str | None = None


def _season_conflict(exc):
    return HTTPException(status_code=409, detail=str(exc))


@olympiad_seasons_page.get('/olympiads/{olympiad_id}/seasons')
async def list_olympiad_seasons(
    olympiad_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    profiles: bool = Query(default=False),
):
    """Сезоны олимпиады: по умолчанию актуальные, архив — отдельным флагом.

    Профили и правила архивного сезона не удаляются: история поступления
    должна оставаться доступной. ``profiles=true`` отдаёт профили сезонов
    одним запросом, чтобы страница олимпиады не делала N+1.
    """
    try:
        if profiles:
            return {
                'seasons': await database.seasons.list_seasons_with_profiles(
                    olympiad_id, include_archived=include_archived
                )
            }
        return {
            'seasons': await database.seasons.list_seasons(
                olympiad_id, include_archived=include_archived
            )
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiad_seasons_page.post('/olympiads/{olympiad_id}/seasons')
async def create_olympiad_season(
    olympiad_id: uuid.UUID,
    body: SeasonCreate,
    current_user: dict = Depends(deps.require_admin),
):
    try:
        # Проверяем олимпиаду заранее: иначе нарушение внешнего ключа
        # неотличимо от дубля сезона и клиент получал бы 409 «сезон уже есть»
        # вместо честного 404.
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        season = await database.seasons.create_season(
            {'olympiad_id': str(olympiad_id), 'season_label': body.season_label}
        )
        await database.audit.log_action(
            'olympiad_season', season['id'], 'create',
            user_id=current_user['id'], after=season,
        )
        return season
    except HTTPException:
        raise
    except database.seasons.SeasonConflict as exc:
        raise _season_conflict(exc) from exc
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
async def update_season(
    season_id: uuid.UUID,
    body: SeasonUpdate,
    current_user: dict = Depends(deps.require_admin),
):
    try:
        existing = await database.seasons.get_season(season_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Season not found')
        data = body.model_dump(exclude_unset=True)
        expected = data.pop('version', None)
        season = await database.seasons.update_season(
            season_id, data, expected_version=expected
        )
        if not season:
            raise HTTPException(status_code=404, detail='Season not found')
        await database.audit.log_action(
            'olympiad_season', season_id, 'update',
            user_id=current_user['id'], after=season,
        )
        return season
    except HTTPException:
        raise
    except database.seasons.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    except database.seasons.SeasonConflict as exc:
        raise _season_conflict(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail='Season with this label already exists for the olympiad',
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.delete('/{season_id}')
async def delete_season(
    season_id: uuid.UUID,
    current_user: dict = Depends(deps.require_admin),
):
    try:
        existing = await database.seasons.get_season(season_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Season not found')
        await database.seasons.delete_season(season_id)
        await database.audit.log_action(
            'olympiad_season', season_id, 'delete',
            user_id=current_user['id'], before=existing,
        )
        return {'deleted': True}
    except HTTPException:
        raise
    except database.seasons.SeasonConflict as exc:
        raise _season_conflict(exc) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.get('/{season_id}/profiles')
async def list_season_profiles(season_id: uuid.UUID):
    try:
        return {'profiles': await database.seasons.list_profiles(season_id)}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@seasons_page.post('/{season_id}/profiles')
async def create_season_profile(
    season_id: uuid.UUID,
    body: ProfileCreate,
    current_user: dict = Depends(deps.require_admin),
):
    try:
        season = await database.seasons.get_season(season_id)
        if not season:
            raise HTTPException(status_code=404, detail='Season not found')
        data = body.model_dump()
        data['season_id'] = str(season_id)
        profile = await database.seasons.create_profile(data)
        await database.audit.log_action(
            'season_profile', profile['id'], 'create',
            user_id=current_user['id'], after=profile,
        )
        return profile
    except HTTPException:
        raise
    except database.seasons.SeasonConflict as exc:
        raise _season_conflict(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail='Profile with this name already exists in the season'
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@profiles_page.put('/{profile_id}')
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdate,
    current_user: dict = Depends(deps.require_admin),
):
    try:
        existing = await database.seasons.get_profile(profile_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Profile not found')
        data = body.model_dump(exclude_unset=True)
        expected = data.pop('version', None)
        profile = await database.seasons.update_profile(
            profile_id, data, expected_version=expected
        )
        if not profile:
            raise HTTPException(status_code=404, detail='Profile not found')
        await database.audit.log_action(
            'season_profile', profile_id, 'update',
            user_id=current_user['id'], before=existing, after=profile,
        )
        return profile
    except HTTPException:
        raise
    except database.seasons.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    except database.seasons.SeasonConflict as exc:
        raise _season_conflict(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail='Profile with this name already exists in the season'
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@profiles_page.delete('/{profile_id}')
async def delete_profile(
    profile_id: uuid.UUID,
    current_user: dict = Depends(deps.require_admin),
):
    try:
        existing = await database.seasons.get_profile(profile_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Profile not found')
        await database.seasons.delete_profile(profile_id)
        await database.audit.log_action(
            'season_profile', profile_id, 'delete',
            user_id=current_user['id'], before=existing,
        )
        return {'deleted': True}
    except HTTPException:
        raise
    except database.seasons.SeasonConflict as exc:
        raise _season_conflict(exc) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
