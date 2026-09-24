import logging
import uuid as uuid_mod

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app import database, schemas
from app.caching.main import (
    cache_olympiad_after_write,
    get_cached_olympiad,
    get_cached_olympiads,
    get_redis,
    invalidate_olympiad,
)
from app.core.cache_guard import safe_cache_write
from app.core.deps import get_current_user, require_org_admin_or_admin


olympiads_page = APIRouter(
    prefix='/olympiads',
    tags=['olympiads'],
)

logger = logging.getLogger('papaya.olympiads')


def _check_own_olympiad(current_user: dict, olympiad: dict) -> None:
    """Object-level: орг-админ правит только олимпиады своей организации.

    Совпадение проверяется по вхождению ``organization_id`` текущего
    пользователя в ``organizer_ids`` олимпиады (JSONB-массив).
    """
    if current_user.get('role') == 'ADMIN':
        return
    own_org = current_user.get('organization_id')
    organizer_ids = olympiad.get('organizer_ids') or []
    if not own_org or not any(
        str(org_id) == str(own_org) for org_id in organizer_ids
    ):
        raise HTTPException(
            status_code=403,
            detail='You can only manage olympiads of your own organization',
        )


@olympiads_page.get(
    '',
    response_model=list[schemas.olympiads.OlympiadResponse],
    responses={
        200: {'description': 'List of olympiads'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        500: {'description': 'Internal server error'},
    },
)
async def list_olympiads(
    status: str | None = Query(default=None),
    organizer_id: uuid_mod.UUID | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    r: aioredis.Redis = Depends(get_redis),
    _: dict = Depends(get_current_user),
):
    try:
        scope = f'status:{status or ""};organizer:{organizer_id or ""};limit:{limit or ""}'
        olympiads = await get_cached_olympiads(
            r,
            scope,
            lambda: database.olympiads.list_olympiads(
                status=status,
                organizer_id=organizer_id,
                limit=limit,
            ),
        )
        return olympiads
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}',
    response_model=schemas.olympiads.OlympiadResponse,
    responses={
        200: {'description': 'Olympiad details'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def get_olympiad(
    olympiad_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    _: dict = Depends(get_current_user),
):
    try:
        olympiad = await get_cached_olympiad(
            r,
            str(olympiad_id),
            lambda: database.olympiads.get_olympiad(str(olympiad_id)),
        )
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        return olympiad
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.post(
    '',
    response_model=schemas.olympiads.OlympiadResponse,
    status_code=201,
    responses={
        201: {'description': 'Olympiad created'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin or organization admin required'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def create_olympiad(
    olympiad: schemas.olympiads.OlympiadCreate,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        create_data = olympiad.model_dump()
        if current_user.get('role') != 'ADMIN':
            # Орг-админ может привязать только свою организацию.
            create_data['organizer_ids'] = [str(current_user['organization_id'])]
        created = await database.olympiads.add_olympiad(create_data)
        await safe_cache_write(cache_olympiad_after_write(r, created))
        return created
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.patch(
    '/{olympiad_id}',
    response_model=schemas.olympiads.OlympiadResponse,
    responses={
        200: {'description': 'Olympiad updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin or organization admin required'},
        404: {'description': 'Olympiad not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def update_olympiad(
    olympiad_id: uuid_mod.UUID,
    update: schemas.olympiads.OlympiadUpdate,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        existing = await get_cached_olympiad(
            r,
            str(olympiad_id),
            lambda: database.olympiads.get_olympiad(str(olympiad_id)),
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Olympiad not found')

        _check_own_olympiad(current_user, existing)

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')

        updated_olympiad = await database.olympiads.edit_olympiad(
            str(olympiad_id),
            update_data,
        )
        if not updated_olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        await safe_cache_write(cache_olympiad_after_write(r, updated_olympiad))
        return updated_olympiad
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.delete(
    '/{olympiad_id}',
    responses={
        200: {'description': 'Olympiad deleted'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin or organization admin required'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def delete_olympiad(
    olympiad_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        existing = await get_cached_olympiad(
            r,
            str(olympiad_id),
            lambda: database.olympiads.get_olympiad(str(olympiad_id)),
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Olympiad not found')

        _check_own_olympiad(current_user, existing)

        deleted = await database.olympiads.delete_olympiad(str(olympiad_id))
        if not deleted:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        await safe_cache_write(invalidate_olympiad(r, str(olympiad_id)))
        return JSONResponse(
            status_code=200,
            content={'deleted': str(olympiad_id)},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')