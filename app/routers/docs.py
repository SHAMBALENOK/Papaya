import hashlib
import logging
import os
import uuid as uuid_mod

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import database, schemas
from app.caching.main import (
    cache_doc_after_write,
    get_cached_doc,
    get_cached_docs,
    get_redis,
    invalidate_doc,
)
from app.core.cache_guard import safe_cache_write
from app.core.config import ALLOWED_DOC_EXTENSIONS, DOCS_DIR, MAX_DOC_MB
from app.core.deps import get_current_user, require_org_admin_or_admin
from app.database.database import get_db


docs_page = APIRouter(
    prefix='/docs',
    tags=['docs'],
)

logger = logging.getLogger('papaya.docs')


def _storage_path(doc_id: uuid_mod.UUID, extension: str) -> str:
    """Путь файла в хранилище: безопасен и предсказуем от id документа."""
    return os.path.join(DOCS_DIR, f'{doc_id}{extension.lower()}')


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _can_access_doc(current_user: dict, doc: dict) -> bool:
    """Object-level доступ к документу: ADMIN — любой, org-admin — свой."""
    if current_user.get('role') == 'ADMIN':
        return True
    org_id = doc.get('organization_id')
    if not org_id:
        return False
    return current_user.get('organization_id') == org_id


@docs_page.get(
    '',
    response_model=list[schemas.docs.DocResponse],
    responses={
        200: {'description': 'List of documents'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        500: {'description': 'Internal server error'},
    },
)
async def list_docs(
    doc_type: str | None = Query(default=None, alias='type'),
    status: str | None = Query(default=None),
    organization_id: uuid_mod.UUID | None = Query(default=None),
    olympiad_id: uuid_mod.UUID | None = Query(default=None),
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(get_current_user),
):
    try:
        if current_user.get('role') != 'ADMIN' and organization_id is None:
            # Организационный представитель видит только документы своей
            # организации (или все свои без фильтра = свои тоже).
            organization_id = current_user.get('organization_id')

        scope = (
            f'type:{doc_type or ""};status:{status or ""};'
            f'org:{organization_id or ""};oly:{olympiad_id or ""}'
        )
        docs = await get_cached_docs(
            r,
            scope,
            lambda: database.docs.list_docs(
                status=status,
                doc_type=doc_type,
                organization_id=str(organization_id) if organization_id else None,
                olympiad_id=str(olympiad_id) if olympiad_id else None,
            ),
        )
        if current_user.get('role') != 'ADMIN':
            docs = [doc for doc in docs if _can_access_doc(current_user, doc)]
        return docs
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.get(
    '/{doc_id}',
    response_model=schemas.docs.DocResponse,
    responses={
        200: {'description': 'Document details'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Invalid token'},
        404: {'description': 'Document not found'},
        500: {'description': 'Internal server error'},
    },
)
async def get_doc(
    doc_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(get_current_user),
):
    try:
        doc = await get_cached_doc(
            r,
            str(doc_id),
            lambda: database.docs.get_doc(str(doc_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        if not _can_access_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        return doc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.post(
    '',
    response_model=schemas.docs.DocResponse,
    status_code=201,
    responses={
        201: {'description': 'Document uploaded'},
        400: {'description': 'Unsupported file format'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin or organization admin required'},
        413: {'description': 'File exceeds the upload size limit'},
        500: {'description': 'Internal server error'},
    },
)
async def upload_doc(
    file: UploadFile = File(...),
    doc_type: str = Query(default='RSOSH_LIST', alias='type'),
    organization_id: uuid_mod.UUID | None = Query(default=None),
    olympiad_id: uuid_mod.UUID | None = Query(default=None),
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        filename = os.path.basename(file.filename or '')
        extension = os.path.splitext(filename)[1].lower()
        if not filename or extension not in ALLOWED_DOC_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f'Unsupported file format. Allowed: {sorted(ALLOWED_DOC_EXTENSIONS)}',
            )
        if doc_type not in ('RSOSH_LIST', 'OLYMPIAD_REGULATION', 'UNIVERSITY_DOCUMENT', 'OTHER'):
            raise HTTPException(status_code=422, detail='Invalid document type')

        if current_user.get('role') != 'ADMIN':
            own_org = current_user.get('organization_id')
            if organization_id is None:
                organization_id = own_org
            if str(organization_id) != str(own_org):
                raise HTTPException(
                    status_code=403,
                    detail='You can only upload documents to your own organization',
                )

        doc_id = uuid_mod.uuid4()
        storage_path = _storage_path(doc_id, extension)
        os.makedirs(DOCS_DIR, exist_ok=True)

        digest = hashlib.sha256()
        written = 0
        max_bytes = MAX_DOC_MB * 1024 * 1024
        try:
            with open(storage_path, 'wb') as file_object:
                while chunk := await file.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f'File exceeds the {MAX_DOC_MB} MB limit',
                        )
                    file_object.write(chunk)
                    digest.update(chunk)

            name = file.filename or f'document{doc_id}'
            created = await database.docs.add_doc(
                {
                    'id': doc_id,
                    'name': name,
                    'type': doc_type,
                    'storage_key': os.path.basename(storage_path),
                    'mime_type': file.content_type,
                    'organization_id': str(organization_id) if organization_id else None,
                    'olympiad_id': str(olympiad_id) if olympiad_id else None,
                    'uploaded_by': str(current_user['id']),
                    'checksum': digest.hexdigest(),
                    'status': 'UPLOADED',
                    'metadata': {
                        'original_name': filename,
                        'bytes': written,
                    },
                }
            )
            await safe_cache_write(cache_doc_after_write(r, created))
            return created
        except HTTPException:
            if os.path.exists(storage_path):
                os.remove(storage_path)
            raise
        except Exception:
            # Сбой БД/кэша после записи файла: не оставляем сироту на диске.
            if os.path.exists(storage_path):
                os.remove(storage_path)
            raise
        finally:
            await file.close()
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.get(
    '/{doc_id}/file',
    responses={
        200: {'description': 'Document file'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Document or file not found'},
        500: {'description': 'Internal server error'},
    },
)
async def download_doc_file(
    doc_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(get_current_user),
):
    try:
        doc = await get_cached_doc(
            r,
            str(doc_id),
            lambda: database.docs.get_doc(str(doc_id)),
        )
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        if not _can_access_doc(current_user, doc):
            raise HTTPException(status_code=403, detail='Permission denied')
        storage_key = doc.get('storage_key')
        if not storage_key:
            raise HTTPException(
                status_code=404,
                detail='Document has no local copy (source_url only)',
            )
        file_path = os.path.realpath(os.path.join(DOCS_DIR, storage_key))
        if (
            os.path.commonpath((DOCS_DIR, file_path)) != DOCS_DIR
            or not os.path.isfile(file_path)
        ):
            raise HTTPException(status_code=404, detail='File not found')
        return FileResponse(
            file_path,
            media_type=doc.get('mime_type') or 'application/octet-stream',
            filename=doc.get('name'),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.patch(
    '/{doc_id}',
    response_model=schemas.docs.DocResponse,
    responses={
        200: {'description': 'Document updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Document not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def update_doc(
    doc_id: uuid_mod.UUID,
    update: schemas.docs.DocUpdate,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        existing = await get_cached_doc(
            r,
            str(doc_id),
            lambda: database.docs.get_doc(str(doc_id)),
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Document not found')
        if not _can_access_doc(current_user, existing):
            raise HTTPException(status_code=403, detail='Permission denied')

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')
        if (
            current_user.get('role') != 'ADMIN'
            and existing.get('organization_id')
            and update_data.get('organization_id')
            and str(update_data['organization_id']) != existing['organization_id']
        ):
            raise HTTPException(
                status_code=403,
                detail='You cannot move a document to another organization',
            )

        updated_doc = await database.docs.edit_doc(str(doc_id), update_data)
        if not updated_doc:
            raise HTTPException(status_code=404, detail='Document not found')
        await safe_cache_write(cache_doc_after_write(r, updated_doc))
        return updated_doc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.delete(
    '/{doc_id}',
    responses={
        200: {'description': 'Document deleted'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Document not found'},
        500: {'description': 'Internal server error'},
    },
)
async def delete_doc(
    doc_id: uuid_mod.UUID,
    r: aioredis.Redis = Depends(get_redis),
    current_user: dict = Depends(require_org_admin_or_admin),
):
    try:
        existing = await get_cached_doc(
            r,
            str(doc_id),
            lambda: database.docs.get_doc(str(doc_id)),
        )
        if not existing:
            raise HTTPException(status_code=404, detail='Document not found')
        if not _can_access_doc(current_user, existing):
            raise HTTPException(status_code=403, detail='Permission denied')

        deleted = await database.docs.delete_doc(str(doc_id))
        if not deleted:
            raise HTTPException(status_code=404, detail='Document not found')

        storage_key = existing.get('storage_key')
        if storage_key:
            file_path = os.path.realpath(os.path.join(DOCS_DIR, storage_key))
            if (
                os.path.commonpath((DOCS_DIR, file_path)) == DOCS_DIR
                and os.path.isfile(file_path)
            ):
                os.remove(file_path)

        await safe_cache_write(invalidate_doc(r, str(doc_id)))
        return JSONResponse(status_code=200, content={'deleted': str(doc_id)})
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')