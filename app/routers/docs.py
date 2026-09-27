"""Документы-источники: загрузка и просмотр.

Документ — источник данных, а не пользовательский объект: его загружает
администратор, он же связывает его с олимпиадами (через
``olympiads.source_doc_id``) и запускает импорт РСОШ. Пользователь видит
документ на странице олимпиады как ответ на вопрос «откуда взялась эта
информация».

Поддерживаемые форматы — те же, что и у импорта РСОШ: PDF, XLSX и
изображения PNG/JPG/JPEG.
"""

import hashlib
import logging
import os
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from werkzeug.utils import secure_filename

from app import database, schemas
from app.core import deps
from app.core.config import ALLOWED_TABLE_EXTENSIONS, DOCS_DIR, MAX_UPLOAD_MB
from app.rsosh import filetypes

docs_page = APIRouter(
    prefix='/docs',
    tags=['documents'],
)

logger = logging.getLogger('papaya.docs')


def _storage_path(doc_id: str, extension: str) -> Path:
    """Путь файла в хранилище: безопасен и предсказуем от id документа."""
    return Path(DOCS_DIR) / f'{doc_id}{extension}'


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_upload(file: UploadFile, target: Path) -> tuple[int, str]:
    """Записать загруженный файл с лимитом размера; вернуть (размер, sha256)."""
    hasher = hashlib.sha256()
    written = 0
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    with open(target, 'wb') as handle:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f'File exceeds the {MAX_UPLOAD_MB} MB limit',
                )
            hasher.update(chunk)
            handle.write(chunk)
    return written, hasher.hexdigest()


@docs_page.get(
    '',
    responses={
        200: {'description': 'Список документов-источников'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_docs(
    doc_type: str | None = Query(default=None, alias='type'),
    status: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    current_user: deps.AdminUser = None,
):
    """Список документов-источников (администратор)."""
    try:
        docs = await database.docs.list_docs(
            doc_type=doc_type,
            status=status,
            limit=limit,
        )
        return {'docs': docs}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.post(
    '/upload',
    response_model=schemas.docs.DocResponse,
    status_code=201,
    responses={
        201: {'description': 'Document uploaded'},
        400: {'description': 'Unsupported file format'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        413: {'description': 'File exceeds the upload size limit'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def upload_doc(
    file: UploadFile = File(...),
    doc_type: str = Form(default='RSOSH_LIST', alias='type'),
    name: str | None = Form(default=None),
    current_user: deps.AdminUser = None,
):
    """Загрузить документ-источник (PDF, XLSX, PNG/JPG/JPEG)."""
    try:
        if doc_type not in schemas.docs.DOC_TYPES:
            raise HTTPException(
                status_code=422,
                detail='Invalid document type. Allowed: '
                + ', '.join(schemas.docs.DOC_TYPES),
            )

        filename = secure_filename(file.filename or '')
        extension = os.path.splitext(filename)[1].lower()
        if not filename or extension not in ALLOWED_TABLE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail='Unsupported file format. Allowed: '
                + ', '.join(sorted(ALLOWED_TABLE_EXTENSIONS)),
            )

        doc_id = uuid.uuid4()
        target = _storage_path(str(doc_id), extension)
        os.makedirs(DOCS_DIR, exist_ok=True)
        try:
            _size, checksum = _read_upload(file, target)
        finally:
            await file.close()

        if not target.is_file() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail='Uploaded file is empty')

        # Сверяем сигнатуру: расширение может быть подделано, а импортёр
        # всё равно откажется работать с неподдерживаемым содержимым.
        try:
            kind = filetypes.detect(str(target))
        except filetypes.RsoshError as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        created = await database.docs.add_doc(
            {
                'id': str(doc_id),
                'name': (name or filename).strip(),
                'type': doc_type,
                'storage_key': target.name,
                'mime_type': kind,
                'checksum': checksum,
                'status': 'UPLOADED',
            }
        )
        return created
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
        403: {'description': 'Admin role required'},
        404: {'description': 'Document not found'},
        500: {'description': 'Internal server error'},
    },
)
async def doc_details(
    doc_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Карточка документа вместе с состоянием импорта РСОШ."""
    try:
        doc = await database.docs.get_doc(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        return doc
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
        403: {'description': 'Admin role required'},
        404: {'description': 'Document or file not found'},
        500: {'description': 'Internal server error'},
    },
)
async def download_doc_file(
    doc_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Скачать файл документа (нужно для проверки, откуда взялись данные)."""
    try:
        doc = await database.docs.get_doc(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        storage_key = doc.get('storage_key')
        if not storage_key:
            raise HTTPException(
                status_code=404,
                detail='Document has no local copy (source_url only)',
            )
        path = _storage_path(str(doc_id), os.path.splitext(storage_key)[1])
        if not path.is_file():
            raise HTTPException(status_code=404, detail='File not found')
        return FileResponse(
            str(path),
            media_type='application/octet-stream',
            filename=doc.get('name') or path.name,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@docs_page.post(
    '/edit_doc/{doc_id}',
    response_model=schemas.docs.DocResponse,
    responses={
        200: {'description': 'Document updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Document not found'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def edit_doc(
    doc_id: uuid.UUID,
    update: schemas.docs.DocUpdate,
    current_user: deps.AdminUser = None,
):
    """Изменить описание документа (имя, тип, примечание)."""
    try:
        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')
        updated = await database.docs.edit_doc(doc_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail='Document not found')
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
