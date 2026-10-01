"""REST-эндпоинты импорта документов РСОШ.

    POST /api/v1/imports/rsosh     — начать импорт документа
    GET  /api/v1/imports           — список прогонов импорта
    GET  /api/v1/imports/{id}      — статус импорта и сводка
    GET  /api/v1/imports/{id}/preview   — кандидаты для подтверждения
    POST /api/v1/imports/{id}/confirm   — применить импорт
    POST /api/v1/imports/{id}/reject    — отклонить результаты

Прогон импорта — это обработка конкретного документа, поэтому идентификатор
прогона совпадает с id документа. Создание и обновление олимпиад происходит
только на ``confirm``: до этого импорт ничего не пишет в каталог.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import database
from app.core import deps
from app.rsosh import processor, states
from app.rsosh.types import RsoshConflictError, RsoshError

imports_page = APIRouter(
    prefix='/imports',
    tags=['imports'],
)

logger = logging.getLogger('papaya.imports')


class RsoshStartRequest(BaseModel):
    doc_id: uuid.UUID


class ConfirmRequest(BaseModel):
    """Подтверждение импорта с выборочным исключением кандидатов.

    ``skip`` — список ``name_norm``, которые НЕ нужно создавать/обновлять
    (администратор снял галочку в окне проверки). Пустое тело — подтвердить
    всё. ``archive_missing`` — перевести в архив олимпиады, исчезнувшие из
    перечня РСОШ (по умолчанию включено; при неполном распознавании
    архивирование автоматически отключается и причина попадает в отчёт).

    Способа «применить устаревший перечень» здесь нет намеренно: подтверждение
    документа, загруженного раньше уже подтверждённого, вернуло бы каталог к
    старой редакции. Такой запрос получает 409, и это не обходится флагом.
    """

    skip: List[str] = Field(default_factory=list)
    archive_missing: bool = True


class ImportListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    type: str | None = None
    status: str | None = None
    state: str | None = None
    summary: dict | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class ImportView(BaseModel):
    """Состояние одного прогона импорта.

    Модель описана явно, чтобы ``/docs`` показывал настоящий ответ: без
    ``response_model`` FastAPI отдаёт пустую схему, и по документации нельзя
    понять, что вообще возвращает маршрут. Набор полей совпадает с
    ``_import_view``.
    """

    id: str
    name: str | None = None
    type: str | None = None
    status: str | None = None
    state: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    summary: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    # Итог применения: created/updated/archived/skipped/errors и
    # archive_skipped_reason. Произвольная структура, поэтому dict.
    confirm: dict | None = None


class ImportConfirmResponse(BaseModel):
    """Ответ на подтверждение импорта."""

    import_: ImportView = Field(alias='import')
    # Что записано в каталог: created, updated, archived, skipped, errors и
    # archive_skipped_reason (почему пропавшие не архивировались).
    result: dict = Field(default_factory=dict)
    # Что администратор снял в preview. Отдельным полем, а не внутри result:
    # это его решение, а не итог записи в каталог.
    skipped: list[str] = Field(default_factory=list)

    model_config = {'populate_by_name': True}


def _import_view(doc: dict) -> dict:
    section = states.rsosh_section(doc)
    return {
        'id': doc['id'],
        'name': doc['name'],
        'type': doc['type'],
        'status': doc['status'],
        'state': section.get('state'),
        'started_at': section.get('started_at'),
        'finished_at': section.get('finished_at'),
        'error': section.get('error'),
        'summary': section.get('summary') or {},
        'warnings': section.get('warnings') or [],
        'confirm': section.get('confirm'),
    }


@imports_page.post(
    '/rsosh',
    status_code=202,
    responses={
        202: {'description': 'Import started (processing in background)'},
        400: {
            'description': (
                'Import is not startable from the current state, or the '
                'document is not a RSOSH_LIST'
            ),
        },
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Document not found'},
        409: {'description': 'Import is already running'},
        500: {'description': 'Internal server error'},
    },
)
async def start_rsosh_import(
    payload: RsoshStartRequest,
    current_user: deps.AdminUser = None,
):
    """Начать импорт документа РСОШ.

    Импортируем только ``RSOSH_LIST``: приказ университета и любой другой
    документ остаются хранилищем источников и олимпиад из них не создают.
    """
    try:
        doc, mode = await processor.start_import(payload.doc_id)
        view = _import_view(doc)
        view['execution'] = mode
        return view
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '',
    responses={
        200: {'description': 'Список прогонов импорта РСОШ'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_imports(
    limit: int | None = Query(default=None, ge=1, le=100),
    current_user: deps.AdminUser = None,
):
    """Список прогонов импорта (только документы РСОШ)."""
    try:
        docs = await database.docs.list_docs(
            doc_type=processor.RSOSH_DOC_TYPE,
            limit=limit,
        )
        return {'imports': [_import_view(doc) for doc in docs]}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/{import_id}',
    response_model=ImportView,
    responses={
        200: {'description': 'Статус импорта'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        500: {'description': 'Internal server error'},
    },
)
async def import_status(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Статус импорта, сводка и предупреждения."""
    try:
        doc = await _rsosh_doc(import_id)
        return _import_view(doc)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/{import_id}/preview',
    responses={
        200: {'description': 'Кандидаты импорта для подтверждения'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is still processing'},
        500: {'description': 'Internal server error'},
    },
)
async def import_preview(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Кандидаты импорта: что будет создано, что обновлено, что требует проверки."""
    try:
        doc = await _rsosh_doc(import_id)
        section = states.rsosh_section(doc)
        if section.get('state') == 'processing':
            raise HTTPException(status_code=409, detail='Import is still processing')
        return {
            'import': _import_view(doc),
            'pages': section.get('pages') or [],
            'candidates': section.get('candidates') or [],
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/confirm',
    response_model=ImportConfirmResponse,
    responses={
        200: {'description': 'Import confirmed and applied'},
        400: {'description': 'Import is not confirmable in its state'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        # Перечень загружен раньше уже подтверждённого либо уже применён.
        # Каталог актуален по последней подтверждённой редакции перечня, и
        # вернуть его назад нельзя — обхода нет.
        409: {'description': 'Snapshot is outdated or already applied'},
        500: {'description': 'Internal server error'},
    },
)
async def confirm(
    import_id: uuid.UUID,
    selection: ConfirmRequest | None = None,
    current_user: deps.AdminUser = None,
):
    """Применить импорт: создать/обновить олимпиады, архивировать пропавшие.

    Ответ 409 означает, что каталог уже соответствует более новому перечню или
    этот перечень уже применён. Повторное и принудительное применение не
    предусмотрено: актуальность каталога задаётся последним подтверждённым
    перечнем РСОШ.
    """
    try:
        # Проверка «документ есть и это RSOSH_LIST» нужна для внятного 404 и
        # выполняется до транзакции. Решающие проверки (состояние перечня и
        # его актуальность) делаются внутри транзакции в persist — эта
        # ничего не решает, только отсекает заведомо неверные запросы.
        await _rsosh_doc(import_id)
        chosen = selection or ConfirmRequest()
        result = await processor.confirm_import(
            import_id,
            skip=chosen.skip,
            archive_missing=chosen.archive_missing,
        )
        doc = result['document']
        return {
            'import': _import_view(doc),
            'result': result['result'],
            # Что администратор снял в preview. Отдаём отдельным полем, а не
            # внутри result: это его решение, а не итог записи в каталог, и по
            # нему видно, что «создано 4 из 5» — намеренно, а не из-за ошибки.
            'skipped': result['skipped'],
        }
    except RsoshConflictError as exc:
        # Состояние каталога не позволяет применить импорт (устаревший снимок
        # или повторное подтверждение) — это конфликт, а не плохой запрос.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/reject',
    responses={
        200: {'description': 'Import rejected (nothing persisted)'},
        400: {'description': 'Import is not rejectable in its state'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        500: {'description': 'Internal server error'},
    },
)
async def reject(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Отклонить результаты импорта (в каталог ничего не пишется)."""
    try:
        doc = await _rsosh_doc(import_id)
        section = states.rsosh_section(doc)
        if section.get('state') not in states.REJECTABLE_STATES:
            raise HTTPException(
                status_code=400,
                detail=f'Import state {section.get("state")} is not rejectable',
            )
        updated = await database.docs.edit_doc(
            doc['id'],
            {
                'metadata': states.docs_metadata_with_section(
                    doc,
                    states.rejected_section(doc),
                ),
                'status': states.DOCS_STATUS['rejected'],
            },
        )
        return _import_view(updated or doc)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _rsosh_doc(import_id: uuid.UUID) -> dict:
    doc = await database.docs.get_doc(import_id)
    if not doc or doc.get('type') != processor.RSOSH_DOC_TYPE:
        raise HTTPException(status_code=404, detail='Import not found')
    return doc
