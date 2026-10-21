"""REST-эндпоинты импорта документов РСОШ и приказов университетов.

РСОШ (создаёт олимпиады каталога):

    POST /api/v1/imports/rsosh     — начать импорт документа
    GET  /api/v1/imports           — список прогонов импорта
    GET  /api/v1/imports/{id}      — статус импорта и сводка
    GET  /api/v1/imports/{id}/preview   — кандидаты для подтверждения
    POST /api/v1/imports/{id}/confirm   — применить импорт
    POST /api/v1/imports/{id}/reject    — отклонить результаты

Приказ вуза (создаёт только заявки БВИ, олимпиад не создаёт):

    POST /api/v1/imports/university            — начать импорт приказа
    GET  /api/v1/imports/university            — список прогонов приказов
    GET  /api/v1/imports/university/{id}       — статус прогона
    GET  /api/v1/imports/university/{id}/preview  — строки и распознанный вуз
    POST /api/v1/imports/university/{id}/confirm  — записать заявки БВИ
    POST /api/v1/imports/university/{id}/reject   — отклонить результаты

Прогон импорта — это обработка конкретного документа, поэтому идентификатор
прогона совпадает с id документа. Создание и обновление олимпиад происходит
только на ``confirm`` перечня РСОШ; приказ вуза на ``confirm`` создаёт лишь
``PENDING``-связи БВИ на существующие олимпиады. Маршруты приказов объявлены
до ``/{import_id}``: статический сегмент ``university`` не должен попадать под
разбор ``import_id`` как UUID.
"""

import logging
import uuid
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import database
from app.core import deps
from app.rsosh import persist, processor, states
from app.rsosh.types import RsoshConflictError, RsoshError
from app.university import persist as university_persist
from app.university import processor as university_processor
from app.university import states as university_states
from app.university.types import (
    UniversityConflictError,
    UniversityError,
)

imports_page = APIRouter(
    prefix='/imports',
    tags=['imports'],
)

logger = logging.getLogger('papaya.imports')


class RsoshStartRequest(BaseModel):
    doc_id: uuid.UUID


class ManualCandidateRequest(BaseModel):
    """Олимпиада, добавленная администратором вручную в меню документа РСОШ."""

    name: str
    description: str | None = None


class ManualCandidateRemoveRequest(BaseModel):
    """Удаление вручную добавленной олимпиады (по нормализованному имени)."""

    name_norm: str


class ConfirmRequest(BaseModel):
    """Подтверждение импорта с выборочным применением кандидатов.

    Применяются только подтверждённые кандидаты: всё, чего нет в ``skip``,
    создаётся/обновляется. ``skip`` — список ``name_norm``, которые НЕ нужно
    создавать/обновлять (администратор снял их в окне проверки).
    ``rename``/``descriptions``/``merge`` — правки распознанных кандидатов до
    записи в каталог: исправленное название, описание и принудительное
    объединение с существующей олимпиадой (её данные обновляются из документа)
    соответственно. Ключи этих словарей — исходные ``name_norm``.
    ``archive_missing`` — перевести в архив олимпиады, исчезнувшие из перечня
    РСОШ (по умолчанию включено; при неполном распознавании архивирование
    автоматически отключается и причина попадает в отчёт).

    Снятые строки полностью исключаются из применения и правок: rename/merge/
    descriptions, оставшиеся для них, не применяются и не проверяются — «снял»
    значит «не трогать».

    Способа «применить устаревший перечень» здесь нет намеренно: подтверждение
    документа, загруженного раньше уже подтверждённого, вернуло бы каталог к
    старой редакции. Такой запрос получает 409, и это не обходится флагом.
    """

    skip: List[str] = Field(default_factory=list)
    archive_missing: bool = True
    # {исходный name_norm: исправленное название} — правка распознанного имени
    # до записи в каталог (см. confirm в persist).
    rename: Dict[str, str] = Field(default_factory=dict)
    # {исходный name_norm: описание}.
    descriptions: Dict[str, str] = Field(default_factory=dict)
    # {исходный name_norm: id существующей олимпиады} — принудительное
    # объединение с олимпиадой из каталога.
    merge: Dict[str, str] = Field(default_factory=dict)


class UniversityStartRequest(BaseModel):
    """Запуск импорта приказа университета."""

    doc_id: uuid.UUID


class UniversitySelectionRequest(BaseModel):
    """Выбор администратора для прогона приказа.

    ``skip`` — строки (``name_norm``), снятые администратором: они не пишутся.
    ``links`` — ручное связывание несопоставленных строк: ``{name_norm: olympiad_id}``
    для строк, которые автоматически не сопоставились с каталогом.
    ``university_id`` — целевой университет приказа, если распознанный из шапки
    не подходит: администратор подтверждает или переопределяет вуз вручную.
    """

    skip: List[str] = Field(default_factory=list)
    links: Dict[str, str] = Field(default_factory=dict)
    university_id: str | None = None


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
    progress: dict | None = None


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
    # Этап обработки (``{"stage": "extracting"}`` и т.п.), пока идёт импорт.
    progress: dict = Field(default_factory=dict)
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
        # Доступность самого источника (ТЗ §7.3) — независимо от того, как
        # прошёл импорт: документ мог обработаться, а ссылка протухнуть.
        'availability': doc.get('availability', 'unknown'),
        'availability_checked_at': doc.get('availability_checked_at'),
        'state': section.get('state'),
        'started_at': section.get('started_at'),
        'finished_at': section.get('finished_at'),
        'error': section.get('error'),
        'progress': section.get('progress') or {},
        'summary': section.get('summary') or {},
        'warnings': section.get('warnings') or [],
        'confirm': section.get('confirm'),
    }


def _university_view(doc: dict) -> dict:
    """Состояние прогона приказа в том же виде, что и у РСОШ.

    Отдельная функция, а не параметр: разделы состояния разные
    (``metadata['university']`` против ``metadata['rsosh']``), и смешивать их
    одним чтением нельзя.
    """
    section = university_states.university_section(doc)
    return {
        'id': doc['id'],
        'name': doc['name'],
        'type': doc['type'],
        'status': doc['status'],
        'availability': doc.get('availability', 'unknown'),
        'availability_checked_at': doc.get('availability_checked_at'),
        'state': section.get('state'),
        'started_at': section.get('started_at'),
        'finished_at': section.get('finished_at'),
        'error': section.get('error'),
        'progress': section.get('progress') or {},
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


@imports_page.post(
    '/university',
    status_code=202,
    responses={
        202: {'description': 'Import started (processing in background)'},
        400: {
            'description': (
                'Import is not startable from the current state, or the '
                'document is not a UNIVERSITY_ORDER'
            ),
        },
        401: {'description': 'Access token missing'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Document not found'},
        409: {'description': 'Import is already running'},
        500: {'description': 'Internal server error'},
    },
)
async def start_university_import(
    payload: UniversityStartRequest,
    current_user: deps.AdminUser = None,
):
    """Начать импорт приказа университета.

    Импортируем только ``UNIVERSITY_ORDER``. Приказ не создаёт олимпиад: на
    подтверждении появятся лишь заявки БВИ (``PENDING``) на существующие
    олимпиады каталога.
    """
    try:
        doc, mode = await university_processor.start_import(payload.doc_id)
        view = _university_view(doc)
        view['execution'] = mode
        return view
    except UniversityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniversityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/university',
    responses={
        200: {'description': 'Список прогонов импорта приказов'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        500: {'description': 'Internal server error'},
    },
)
async def list_university_imports(
    limit: int | None = Query(default=None, ge=1, le=100),
    current_user: deps.AdminUser = None,
):
    """Список прогонов импорта приказов университетов."""
    try:
        docs = await database.docs.list_docs(
            doc_type=university_processor.UNIVERSITY_DOC_TYPE,
            limit=limit,
        )
        return {'imports': [_university_view(doc) for doc in docs]}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/university/{import_id}',
    responses={
        200: {'description': 'Статус импорта приказа'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        500: {'description': 'Internal server error'},
    },
)
async def university_import_status(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Статус импорта приказа, сводка и предупреждения."""
    try:
        doc = await _university_doc(import_id)
        return _university_view(doc)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/university/{import_id}/preview',
    responses={
        200: {'description': 'Строки приказа и распознанный вуз'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is still processing'},
        500: {'description': 'Internal server error'},
    },
)
async def university_import_preview(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Строки приказа: что сопоставлено, что требует ручного связывания.

    Отдаёт кандидатов, распознанный из шапки вуз и сохранённый выбор
    администратора. Каталог и связи на этом шаге не меняются.
    """
    try:
        doc = await _university_doc(import_id)
        section = university_states.university_section(doc)
        if section.get('state') == 'processing':
            raise HTTPException(status_code=409, detail='Import is still processing')
        return {
            'import': _university_view(doc),
            'pages': section.get('pages') or [],
            'university': section.get('university') or {},
            'candidates': section.get('candidates') or [],
            'selection': section.get('selection'),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.put(
    '/university/{import_id}/selection',
    responses={
        200: {'description': 'Selection saved'},
        400: {'description': 'Unknown candidates in selection'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is not ready for review'},
        500: {'description': 'Internal server error'},
    },
)
async def save_university_selection(
    import_id: uuid.UUID,
    payload: UniversitySelectionRequest,
    current_user: deps.AdminUser = None,
):
    """Сохранить выбор администратора (снятые строки, ручные связи, вуз)."""
    try:
        await _university_doc(import_id)
        doc = await university_persist.save_import_selection(
            import_id, selection=payload.model_dump()
        )
        return _university_view(doc)
    except UniversityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniversityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/university/{import_id}/confirm',
    responses={
        200: {'description': 'Import confirmed: PENDING BVI links created'},
        400: {'description': 'Import is not confirmable in its state'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is already applied or still processing'},
        500: {'description': 'Internal server error'},
    },
)
async def confirm_university_import(
    import_id: uuid.UUID,
    selection: UniversitySelectionRequest | None = None,
    current_user: deps.AdminUser = None,
):
    """Применить импорт приказа: создать заявки БВИ (``PENDING``).

    Олимпиады каталога не создаются и не изменяются, связи не подтверждаются:
    их подтверждает модератор отдельным действием. Тело запроса не задано —
    применяется сохранённый выбор администратора.
    """
    try:
        doc = await _university_doc(import_id)
        if selection is not None:
            chosen = selection
        else:
            stored = university_states.university_section(doc).get('selection')
            chosen = (
                UniversitySelectionRequest(**stored)
                if stored
                else UniversitySelectionRequest()
            )
        result = await university_processor.confirm_import(
            import_id,
            selection=chosen.model_dump(),
            university_id=chosen.university_id,
        )
        return {
            'import': _university_view(result['document']),
            'result': result['result'],
        }
    except UniversityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniversityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/university/{import_id}/reject',
    responses={
        200: {'description': 'Import rejected (nothing persisted)'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is already applied or is being processed'},
        500: {'description': 'Internal server error'},
    },
)
async def reject_university_import(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Отклонить результаты импорта приказа (ни каталог, ни связи не трогаются)."""
    try:
        await _university_doc(import_id)
        rejected = await university_persist.reject_import(import_id)
        return _university_view(rejected)
    except UniversityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniversityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/university/{import_id}/pause',
    responses={
        200: {'description': 'Import pause requested / paused'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is not being processed'},
        500: {'description': 'Internal server error'},
    },
)
async def pause_university_import(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Приостановить идущую обработку приказа."""
    try:
        await _university_doc(import_id)
        doc = await university_persist.request_pause(import_id)
        return _university_view(doc)
    except UniversityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniversityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/university/{import_id}/resume',
    responses={
        200: {'description': 'Import resumed (processing in background)'},
        400: {'description': 'Document is not startable'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is not paused'},
        500: {'description': 'Internal server error'},
    },
)
async def resume_university_import(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Возобновить приостановленный импорт приказа."""
    try:
        doc, mode = await university_processor.resume_import(import_id)
        view = _university_view(doc)
        view['execution'] = mode
        return view
    except UniversityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniversityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
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
        # Вручную добавленные олимпиады показываются вместе с распознанными:
        # для администратора это единый список строк перечня.
        candidates = list(section.get('candidates') or []) + list(
            section.get('manual_candidates') or []
        )
        return {
            'import': _import_view(doc),
            'pages': section.get('pages') or [],
            'candidates': candidates,
            # Сохранённый ранее выбор администратора (если есть): панель
            # восстанавливает по нему подтверждённые/снятые строки и правки.
            'selection': section.get('selection'),
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
        doc = await _rsosh_doc(import_id)
        if selection is not None:
            chosen = selection
        else:
            # Тело не задано — применяем сохранённый выбор администратора.
            # Пустое тело (``{}``) и сохранённый выбор ведут себя по-разному:
            # ``{}`` означает «подтвердить всё» и сохранённый выбор не
            # подменяет, а отсутствие тела — «что решили ранее».
            stored = states.rsosh_section(doc).get('selection')
            chosen = ConfirmRequest(**stored) if stored else ConfirmRequest()
        result = await processor.confirm_import(
            import_id,
            skip=chosen.skip,
            rename=chosen.rename,
            descriptions=chosen.descriptions,
            merge=chosen.merge,
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
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        # Состояние не позволяет отклонить: в частности, прогон уже применён
        # (approved) — его нельзя ни подтвердить повторно, ни отклонить.
        409: {'description': 'Import is already applied or is being processed'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def reject(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Отклонить результаты импорта (в каталог ничего не пишется).

    Отклонение меняет только состояние прогона, но делает это под той же
    блокировкой, что и подтверждение: иначе ``reject`` мог бы отработать уже
    после того, как ``confirm`` применил перечень, и прогон выглядел бы
    отклонённым при уже изменённом каталоге.
    """
    try:
        await _rsosh_doc(import_id)
        rejected = await persist.reject_confirmed_import(import_id)
        return _import_view(rejected)
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/pause',
    responses={
        200: {'description': 'Import pause requested / paused'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is not being processed'},
        500: {'description': 'Internal server error'},
    },
)
async def pause_import(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Приостановить идущую обработку документа.

    Приостановка срабатывает на границе этапа: сразу после запуска импорт
    останавливается до тяжёлого чтения, а уже читающий документ — по
    завершении чтения. В ответе ``processing`` с флагом паузы означает, что
    запрос принят и обработка остановится на ближайшей границе; ``paused`` —
    что она уже остановлена.
    """
    try:
        await _rsosh_doc(import_id)
        doc = await persist.request_pause(import_id)
        return _import_view(doc)
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/resume',
    responses={
        200: {'description': 'Import resumed (processing in background)'},
        400: {'description': 'Document is not startable'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is not paused'},
        500: {'description': 'Internal server error'},
    },
)
async def resume_import(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Возобновить приостановленный импорт.

    Если приостановка сохранила распознанные строки, обработка продолжается с
    сопоставления — документ не читается заново. Иначе обработка начинается с
    начала.
    """
    try:
        doc, mode = await processor.resume_import(import_id)
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


@imports_page.put(
    '/{import_id}/selection',
    responses={
        200: {'description': 'Selection saved'},
        400: {'description': 'Unknown candidates in selection'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is not ready for review'},
        500: {'description': 'Internal server error'},
    },
)
async def save_selection(
    import_id: uuid.UUID,
    payload: ConfirmRequest,
    current_user: deps.AdminUser = None,
):
    """Сохранить выбор администратора вместе с прогоном.

    Сохранённый выбор переживает перезагрузку страницы и применяется при
    подтверждении, если тело запроса ``confirm`` не задано. Сам по себе выбор
    каталог не меняет.
    """
    try:
        await _rsosh_doc(import_id)
        doc = await persist.save_import_selection(
            import_id, selection=payload.model_dump()
        )
        return _import_view(doc)
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/candidates',
    responses={
        200: {'description': 'Olympiad added to the import document'},
        400: {'description': 'Invalid candidate (empty name) or not a RSOSH list'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is confirmed/rejected or duplicate candidate'},
        500: {'description': 'Internal server error'},
    },
)
async def add_manual_candidate(
    import_id: uuid.UUID,
    payload: ManualCandidateRequest,
    current_user: deps.AdminUser = None,
):
    """Добавить олимпиаду в документ РСОШ вручную.

    Пока документ не подтверждён и не отклонён, администратор может дополнить
    перечень олимпиадой, которой не нашлось в распознанном списке. При
    подтверждении такая олимпиада создаётся с источником — этим документом.
    """
    try:
        await _rsosh_doc(import_id)
        doc = await persist.add_manual_candidate(
            import_id,
            name=payload.name,
            description=payload.description,
        )
        return _import_view(doc)
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/candidates/remove',
    responses={
        200: {'description': 'Manual olympiad removed from the import document'},
        400: {'description': 'Candidate not found or not a RSOSH list'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Import is confirmed/rejected'},
        500: {'description': 'Internal server error'},
    },
)
async def remove_manual_candidate(
    import_id: uuid.UUID,
    payload: ManualCandidateRemoveRequest,
    current_user: deps.AdminUser = None,
):
    """Убрать вручную добавленную олимпиаду из документа РСОШ."""
    try:
        await _rsosh_doc(import_id)
        doc = await persist.remove_manual_candidate(
            import_id, name_norm=payload.name_norm
        )
        return _import_view(doc)
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


async def _university_doc(import_id: uuid.UUID) -> dict:
    doc = await database.docs.get_doc(import_id)
    if not doc or doc.get('type') != university_processor.UNIVERSITY_DOC_TYPE:
        raise HTTPException(status_code=404, detail='Import not found')
    return doc
