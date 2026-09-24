import logging
import uuid as uuid_mod

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app import database, schemas
from app.caching.main import (
    cache_organization_after_write,
    get_cached_organization,
    get_cached_organizations,
    get_redis,
    invalidate_organization,
)
from app.core.cache_guard import safe_cache_write
from app.core.deps import get_current_user, require_admin, require_org_admin_or_admin


organizations_page = APIRouter(
    prefix='/organizations',
    tags=['organizations'],
)

logger = logging.getLogger('papaya.organizations')


@organizations_page.get(
    '',
    response_model=list[schemas.organizations.OrganizationResponse],
    responses={
        200: {'description': 'List of organizations'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        500: {'description': 'Internal server error'},
    },
)
async def list_organizations(
    org_type: str | None = Query(default=None, alias='type'),
    limit: int | None = Query(default=None, ge=1, le=500),
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(get_current_user),
):
    try:
        own_org = None
        if current_user.get('role') == 'ORGANIZATION_ADMIN':
            # Представитель организации видит в списке только свою.
            own_org = str(current_user.get('organization_id') or '')
        scope = f'all:{org_type or ""};limit:{limit or ""};org:{own_org or ""}'
        orgs = await get_cached_organizations(
            r,
            scope,
            lambda: database.organizations.list_organizations(
                org_type=org_type,
                limit=limit,
            ),
        )
        if own_org:
            orgs = [org for org in orgs if org.get('id') == own_org]
        return orgs
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@organizations_page.get(
    '/{org_id}',
    response_model=schemas.organizations.OrganizationResponse,
    responses={
        200: {'description': 'Organization details'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        404: {'description': 'Organization not found'},
        500: {'description': 'Internal server error'},
    },
)
async def get_organization(
    org_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    _: dict = Depends(get_current_user),
):
    try:
        org = await get_cached_organization(
            r,
            str(org_id),
            lambda: database.organizations.get_organization(str(org_id)),
        )
        if not org:
            raise HTTPException(status_code=404, detail='Organization not found')
        return org
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@organizations_page.post(
    '',
    response_model=schemas.organizations.OrganizationResponse,
    status_code=201,
    responses={
        201: {'description': 'Organization created'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def create_organization(
    org: schemas.organizations.OrganizationCreate,
    r: aioredis.Redis = Depends(get_redis),
    _: dict = Depends(require_admin),
):
    try:
        created = await database.organizations.add_organization(org.model_dump())
        await safe_cache_write(cache_organization_after_write(r, created))
        return created
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@organizations_page.patch(
    '/{org_id}',
    response_model=schemas.organizations.OrganizationResponse,
    responses={
        200: {'description': 'Organization updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Organization not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def update_organization(
    org_id: uuid_mod.UUID,
    update: schemas.organizations.OrganizationUpdate,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        existing = await get_cached_organization(
            r,
            str(org_id),
            lambda: database.organizations.get_organization(str(org_id)),
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Organization not found')

        _check_own_org(current_user, str(org_id))

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')

        updated_org = await database.organizations.edit_organization(
            str(org_id),
            update_data,
        )
        if not updated_org:
            raise HTTPException(status_code=404, detail='Organization not found')
        await safe_cache_write(cache_organization_after_write(r, updated_org))
        return updated_org
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@organizations_page.delete(
    '/{org_id}',
    responses={
        200: {'description': 'Organization deleted'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Organization not found'},
        500: {'description': 'Internal server error'},
    },
)
async def delete_organization(
    org_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        existing = await get_cached_organization(
            r,
            str(org_id),
            lambda: database.organizations.get_organization(str(org_id)),
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Organization not found')

        _check_own_org(current_user, str(org_id))

        deleted = await database.organizations.delete_organization(str(org_id))
        if not deleted:
            raise HTTPException(status_code=404, detail='Organization not found')
        await safe_cache_write(invalidate_organization(r, str(org_id)))
        return JSONResponse(status_code=200, content={'deleted': str(org_id)})
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


def _check_own_org(current_user: dict, org_id: str) -> None:
    """Object-level: представитель организации правит только свою организацию."""
    if current_user.get('role') == 'ADMIN':
        return
    own_org = current_user.get('organization_id')
    if own_org != org_id:
        raise HTTPException(
            status_code=403,
            detail='You can only manage your own organization',
        )