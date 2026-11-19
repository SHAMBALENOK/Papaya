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
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import database
from app.core import deps
from app.rsosh import (
    list_processor,
    persist,
    processor,
    states,
    university as university_import,
)
from app.rsosh.types import RsoshConflictError, RsoshError

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


class PlanOlympiadChange(BaseModel):
    """Правка сопоставления одной олимпиады в плане импорта."""

    name_norm: str
    action: str | None = None
    olympiad_id: str | None = None
    name: str | None = None
    organizer: str | None = None


class PlanProfileChange(BaseModel):
    """Правка профиля сезона: название, уровень или действие."""

    olympiad: str
    source_row: int
    action: str | None = None
    name: str | None = None
    level: str | None = None


class PlanUpdateRequest(BaseModel):
    """Правки плана импорта официального перечня.

    Правки адресуются по нормализованному названию олимпиады и номеру строки
    профиля, поэтому их можно присылать в любом порядке и частями.
    """

    olympiads: List[PlanOlympiadChange] = Field(default_factory=list)
    profiles: List[PlanProfileChange] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    """Применение плана: фиксировать ли отсутствие олимпиад."""

    mark_missing: bool = False


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


@imports_page.post(
    '/university',
    status_code=202,
    responses={202: {'description': 'University document processed'}},
)
async def start_university_import(
    payload: RsoshStartRequest,
    current_user: deps.AdminUser = None,
):
    try:
        doc = await university_import.run_university_import(payload.doc_id)
        return {'id': doc['id'], 'status': doc['status'], 'metadata': doc.get('metadata')}
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


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
    # Официальный перечень: режим, заголовок и связанные таблицы. Панель по
    # этим полям понимает, показывать карточки кандидатов или план с таблицей.
    mode: str | None = None
    title: str | None = None
    table: dict | None = None
    html: dict | None = None
    applied_at: str | None = None
    history_count: int = 0


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
        'progress': section.get('progress') or {},
        'summary': section.get('summary') or {},
        'warnings': section.get('warnings') or [],
        'confirm': section.get('confirm'),
        'mode': section.get('mode'),
        'title': section.get('title'),
        'table': section.get('table'),
        'html': section.get('html'),
        'applied_at': section.get('applied_at'),
        'history_count': len(section.get('history') or []),
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
        await database.imports.start_job(
            payload.doc_id, kind='RSOSH', user_id=current_user.get('id')
        )
        await database.audit.log_action(
            'import', payload.doc_id, 'start',
            user_id=current_user.get('id'), after={'execution': mode},
        )
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


@imports_page.get(
    '/{import_id}/plan',
    responses={
        200: {'description': 'План импорта официального перечня'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'План ещё не построен'},
        500: {'description': 'Internal server error'},
    },
)
async def import_plan(
    import_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """План импорта: что создать, что использовать, чего не хватает.

    План — предмет проверки для официального перечня. Он отдаётся целиком:
    администратор должен видеть все строки документа, а не только спорные,
    иначе нельзя заметить потерянную при OCR олимпиаду.
    """
    try:
        doc = await _rsosh_doc(import_id)
        section = states.rsosh_section(doc)
        plan = section.get('plan')
        if not plan:
            raise HTTPException(
                status_code=409,
                detail='План импорта ещё не построен: документ не разобран',
            )
        return {'import': _import_view(doc), 'plan': plan}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.patch(
    '/{import_id}/plan',
    responses={
        200: {'description': 'План обновлён'},
        400: {'description': 'Некорректная правка плана'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'План ещё не построен или импорт уже применён'},
        500: {'description': 'Internal server error'},
    },
)
async def update_import_plan(
    import_id: uuid.UUID,
    payload: PlanUpdateRequest,
    current_user: deps.AdminUser = None,
):
    """Исправить сопоставление, название, уровень или действие в плане.

    Правки не пишут в каталог: они меняют только план. Запись происходит
    отдельным шагом — применением, и только один раз.
    """
    try:
        doc = await _rsosh_doc(import_id)
        section = states.rsosh_section(doc)
        if not section.get('plan'):
            raise HTTPException(
                status_code=409,
                detail='План импорта ещё не построен',
            )
        if section.get('applied_at') or section.get('state') == 'approved':
            raise HTTPException(
                status_code=409,
                detail='Импорт уже применён: план больше не редактируется',
            )
        updated = await list_processor.update_plan(
            import_id, payload.model_dump(exclude_none=True)
        )
        await database.audit.log_action(
            'import', import_id, 'plan_update',
            user_id=current_user.get('id'),
        )
        return {
            'import': _import_view(updated),
            'plan': states.rsosh_section(updated).get('plan'),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.post(
    '/{import_id}/apply',
    responses={
        200: {'description': 'План применён, каталог обновлён'},
        400: {'description': 'План неполон: есть неразрешённые строки'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Импорт уже применён'},
        500: {'description': 'Internal server error'},
    },
)
async def apply_import_plan(
    import_id: uuid.UUID,
    payload: ApplyRequest | None = None,
    current_user: deps.AdminUser = None,
):
    """Применить утверждённый план одной транзакцией.

    ``mark_missing`` фиксирует отсутствие олимпиад: профили, которых нет в
    перечне, теряют уровень, а олимпиады уходят в архив. Это возможно только
    по полному перечню — частичный скан не доказывает отсутствие.
    """
    try:
        doc = await _rsosh_doc(import_id)
        section = states.rsosh_section(doc)
        if section.get('mode') != 'official_list':
            raise HTTPException(
                status_code=400,
                detail='Документ обработан прежним конвейером: используйте '
                       'confirm',
            )
        outcome = await list_processor.apply(
            import_id,
            user_id=current_user.get('id'),
            mark_missing=bool(payload.mark_missing) if payload else False,
        )
        await database.audit.log_action(
            'import', import_id, 'apply',
            user_id=current_user.get('id'), after=outcome.get('result'),
        )
        updated = await _rsosh_doc(import_id)
        return {
            'import': _import_view(updated),
            'result': outcome.get('result') or {},
            'records': outcome.get('records') or [],
            'history': outcome.get('history') or [],
            'missing_profiles': outcome.get('missing_profiles') or [],
        }
    except HTTPException:
        raise
    except RsoshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RsoshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/{import_id}/history',
    responses={
        200: {'description': 'История изменений каталога по документу'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        500: {'description': 'Internal server error'},
    },
)
async def import_history(
    import_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: deps.AdminUser = None,
):
    """Что этот документ изменил в каталоге.

    История хранится в метаданных документа: она описывает решения по этому
    перечню (создание, переименование, смена уровня, отсутствие), а не общий
    журнал аудита.
    """
    try:
        doc = await _rsosh_doc(import_id)
        section = states.rsosh_section(doc)
        history = list(section.get('history') or [])
        jobs = await database.imports.list_jobs(doc_id=import_id, limit=20)
        return {
            'import': _import_view(doc),
            'history': history[-limit:],
            'confirm': section.get('confirm'),
            'jobs': jobs,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@imports_page.get(
    '/{import_id}/table',
    responses={
        200: {'description': 'Страница таблицы перечня'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Import not found'},
        409: {'description': 'Таблица ещё не собрана'},
        500: {'description': 'Internal server error'},
    },
)
async def import_table(
    import_id: uuid.UUID,
    sheet: str = Query(default='list', pattern='^(list|summary)$'),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None, max_length=100),
    current_user: deps.AdminUser = None,
):
    """Постраничный просмотр таблицы перечня (лист перечня или сводки).

    Пагинация серверная: в перечне бывает 300+ строк, и отдавать их все в
    одном ответе незачем. Поиск фильтрует по всем колонкам листа.
    """
    try:
        await _rsosh_doc(import_id)
        page = await list_processor.table_page(
            import_id, sheet=sheet, offset=offset, limit=limit, search=search
        )
        return page
    except HTTPException:
        raise
    except RsoshError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        if states.rsosh_section(doc).get('mode') == 'official_list':
            raise HTTPException(
                status_code=409,
                detail='Это официальный перечень: примените план через '
                       '/imports/{id}/apply, а не подтверждение кандидатов',
            )
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
        outcome = result['result']
        records = []
        for key, action, status in (
            ('created', 'create', 'created'),
            ('updated', 'merge', 'updated'),
            ('archived', 'archive', 'archived'),
            ('skipped', 'skip', 'skipped'),
            ('errors', 'error', 'error'),
        ):
            for name in outcome.get(key) or []:
                records.append(
                    {'name': str(name), 'action': action, 'status': status}
                )
        await database.imports.finish_open_job(
            import_id, status='APPLIED', summary=outcome, records=records,
        )
        await database.audit.log_action(
            'import', import_id, 'confirm',
            user_id=current_user.get('id'), after=result['result'],
        )
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
        await database.imports.finish_open_job(
            import_id, status='REJECTED', error='Rejected by administrator'
        )
        await database.audit.log_action(
            'import', import_id, 'reject',
            user_id=current_user.get('id'), after=rejected,
        )
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
