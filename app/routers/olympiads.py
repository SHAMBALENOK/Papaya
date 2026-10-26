"""Каталог олимпиад.

Каталог читается публично: это второй шаг основного сценария
«университет → олимпиада → официальный сайт». Создавать и править олимпиады
может только администратор Papaya — вручную или через импорт документов РСОШ
(см. ``app/routers/imports.py``). Представитель университета олимпиаду не
создаёт: он выбирает существующую из каталога.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app import database, schemas
from app.core import audit, deps
from app.models.benefit_rules import BENEFIT_TYPES
from app.routers.docs import document_file_response, document_has_local_file

olympiads_page = APIRouter(
    prefix='/olympiads',
    tags=['olympiads'],
)

logger = logging.getLogger('papaya.olympiads')


# Публичная строка каталога описана в схемах: одна формулировка на
# /olympiads и /search, чтобы поля не расходились.
OlympiadListItem = schemas.olympiads.OlympiadListItem


class OlympiadsResponse(BaseModel):
    olympiads: List[OlympiadListItem]
    # Всего олимпиад под фильтром — чтобы клиент отличал «конец списка» от
    # «показана только первая страница» (ТЗ §10.1).
    total: int = 0


#: Заголовок источника для олимпиады, созданной вручную. Такой записи нет в
#: перечне РСОШ, и это нужно сказать прямо, а не молча показать пустоту.
MANUAL_SOURCE_TITLE = 'Создано администратором Papaya'

#: Заголовок источника для записи из документа РСОШ, у которого нет названия.
RSOSH_SOURCE_TITLE = 'Перечень олимпиад РСОШ'


class SourceInfo(BaseModel):
    """Откуда взялась информация об олимпиаде.

    ``title`` — что стало источником данных: название документа-источника
    (загруженного перечня РСОШ) либо прямое указание на ручное создание
    администратором. ``has_file`` — есть ли у документа локальная копия файла,
    которую можно скачать через ``/olympiads/{id}/source/file``. Внутренние
    детали документа (UUID, хеш, статус обработки, metadata) здесь не отдаются:
    ответ на вопрос «откуда это» не должен быть доступом к устройству импорта.
    """

    title: str | None = None
    has_file: bool = False


def _serialize(olympiad: dict) -> dict:
    """Публичное представление олимпиады.

    ``source_doc_id`` намеренно не попадает в ответ: это внутренняя ссылка на
    загруженный документ, пользователю она ничего не даёт, а раскрывает
    устройство импорта. Для источника есть отдельный маршрут
    ``/olympiads/{id}/source``. ``archive_reason`` — тоже внутреннее поле:
    в списке посетителю достаточно ``status`` и ``is_archived``.
    """
    return {
        'id': olympiad.get('id'),
        'name': olympiad.get('name'),
        'description': olympiad.get('description'),
        'official_url': olympiad.get('official_url'),
        'organizer': olympiad.get('organizer'),
        'preview_image': olympiad.get('preview_image'),
        'image': olympiad.get('image'),
        'status': olympiad.get('status'),
        'is_archived': olympiad.get('status') != 'PUBLISHED',
    }


@olympiads_page.get(
    '',
    response_model=OlympiadsResponse,
    responses={
        200: {'description': 'Каталог олимпиад'},
        500: {'description': 'Internal server error'},
    },
)
async def list_olympiads(
    search: str | None = Query(default=None, description='Поиск по названию и описанию'),
    include_archived: bool = Query(
        default=False,
        description='Показать архивные олимпиады (вне актуального перечня РСОШ)',
    ),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Каталог олимпиад — публичное чтение без авторизации."""
    try:
        status = None if include_archived else 'PUBLISHED'
        olympiads = await database.olympiads.list_olympiads(
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = await database.olympiads.count_olympiads(status=status, search=search)
        return {
            'olympiads': [_serialize(item) for item in olympiads],
            'total': total,
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}',
    response_model=schemas.olympiads.OlympiadPublicResponse,
    responses={
        200: {'description': 'Olympiad details'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_details(olympiad_id: uuid.UUID):
    """Страница олимпиады (публичная карточка, без внутренних id документов)."""
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        return olympiad
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/source',
    response_model=SourceInfo,
    responses={
        200: {'description': 'Источник данных об олимпиаде'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_source(olympiad_id: uuid.UUID):
    """Откуда взялась информация об олимпиаде.

    Отвечает всегда (кроме несуществующей олимпиады): у Papaya два нормальных
    источника — документ РСОШ (называем его именем) и ручной ввод
    администратора, и оба надо называть прямо.

    - импорт РСОШ → ``title`` = название документа-источника;
    - ручное создание → ``title`` = «Создано администратором Papaya».

    ``has_file`` говорит, есть ли файл документа, который действительно
    скачивается через ``/olympiads/{id}/source/file``. Этот маршрут отдаёт
    документ только опубликованной олимпиады, поэтому у архивной записи
    ``has_file`` всегда ``false``: интерфейс не должен показывать кнопку
    скачивания, ведущую в 404. Наличие файла проверяется по диску, а не только
    по ``storage_key``. Служебные поля документа (UUID, хеш, статус обработки)
    наружу не отдаются.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')

        title = MANUAL_SOURCE_TITLE
        has_file = False

        doc_id = olympiad.get('source_doc_id')
        if doc_id:
            doc = await database.docs.get_doc(uuid.UUID(str(doc_id)))
            if doc:
                title = doc.get('name') or RSOSH_SOURCE_TITLE
                has_file = (
                    olympiad.get('status') == 'PUBLISHED'
                    and document_has_local_file(doc)
                )

        return SourceInfo(title=title, has_file=has_file)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/source/file',
    responses={
        200: {'description': 'Файл документа-источника олимпиады'},
        404: {'description': 'Olympiad, source document or file not found'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_source_file(olympiad_id: uuid.UUID):
    """Скачать файл документа-источника опубликованной олимпиады.

    Публичный доступ выдаётся не к произвольным документам, а только к файлу,
    привязанному к опубликованной олимпиаде: это данные, на которых основана
    карточка, и пользователь должен иметь возможность их проверить.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad or olympiad.get('status') != 'PUBLISHED':
            raise HTTPException(status_code=404, detail='Document not found')

        doc_id = olympiad.get('source_doc_id')
        if not doc_id:
            raise HTTPException(status_code=404, detail='Document not found')

        doc = await database.docs.get_doc(uuid.UUID(str(doc_id)))
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')

        return document_file_response(doc)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/universities',
    response_model=schemas.benefit_rules.UniversitiesWithRulesResponse,
    responses={
        200: {'description': 'Университеты с правилами льгот по этой олимпиаде'},
        404: {'description': 'Olympiad not found'},
        422: {'description': 'Недопустимое значение фильтра'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_universities(
    olympiad_id: uuid.UUID,
    benefit_type: str | None = Query(default=None, description='Фильтр по виду льготы'),
    subject: str | None = Query(default=None, description='Фильтр по предмету'),
    season_id: uuid.UUID | None = Query(default=None, description='Фильтр по сезону'),
    profile_id: uuid.UUID | None = Query(default=None, description='Фильтр по профилю'),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Университеты, дающие льготы за олимпиаду, вместе с правилами.

    Публично видны только опубликованные и не отклонённые правила; черновики
    публичным фактом не являются. Правило без сезона относится к олимпиаде в
    целом и при фильтре по сезону не показывается.

    Если олимпиада архивная, правила остаются в списке с ``is_historical``:
    университеты действительно давали льготу, пока олимпиада была в перечне
    РСОШ. Удалять их из-за архива нельзя — это стёрло бы историю.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        if benefit_type is not None and benefit_type not in BENEFIT_TYPES:
            raise HTTPException(
                status_code=422,
                detail='benefit_type must be one of ' + ', '.join(BENEFIT_TYPES),
            )
        filters = dict(
            benefit_type=benefit_type,
            subject=subject,
            season_id=season_id,
            profile_id=profile_id,
            public_only=True,
        )
        universities = await database.benefit_rules.list_universities_for_olympiad(
            olympiad_id, limit=limit, offset=offset, **filters
        )
        total = await database.benefit_rules.count_universities_for_olympiad(
            olympiad_id, **filters
        )
        return {'universities': universities, 'total': total}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/benefit-facets',
    response_model=schemas.benefit_rules.BenefitRuleFacets,
    responses={
        200: {'description': 'Значения фильтров по правилам олимпиады'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_benefit_facets(olympiad_id: uuid.UUID):
    """Виды льгот, предметы и сезоны, по которым есть опубликованные правила."""
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        return await database.benefit_rules.rule_facets(
            olympiad_id=olympiad_id, public_only=True
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/seasons',
    response_model=schemas.seasons.SeasonsResponse,
    responses={
        200: {'description': 'Сезоны олимпиады'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_seasons(olympiad_id: uuid.UUID):
    """Сезоны олимпиады — от нового года к старому (ТЗ §4.4).

    Сезон — отдельная сущность: уровень РСОШ, даты, состояние и профили
    относятся к конкретному году. Публичное чтение.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        seasons = await database.seasons.list_seasons(olympiad_id)
        return {'seasons': seasons}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/seasons/{season_id}',
    response_model=schemas.seasons.SeasonWithProfiles,
    responses={
        200: {'description': 'Сезон с профилями'},
        404: {'description': 'Season not found'},
        500: {'description': 'Internal server error'},
    },
)
async def season_details(olympiad_id: uuid.UUID, season_id: uuid.UUID):
    """Сезон с профилями (публичное чтение)."""
    try:
        season = await database.seasons.get_season(season_id)
        if not season or str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(status_code=404, detail='Season not found')
        return season
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.put(
    '/{olympiad_id}/seasons/{year}',
    response_model=schemas.seasons.SeasonItem,
    responses={
        200: {'description': 'Сезон создан или обновлён'},
        400: {'description': 'Недопустимое состояние сезона'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def upsert_season(
    olympiad_id: uuid.UUID,
    year: int,
    body: schemas.seasons.SeasonUpsert,
    current_user: deps.AdminUser = None,
):
    """Создать/обновить сезон олимпиады (администратор)."""
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        try:
            season = await database.seasons.upsert_season(
                olympiad_id,
                year=year,
                label=body.label,
                rsoh_level=body.rsoh_level,
                state=body.state,
                dates=body.dates,
                description=body.description,
                source_url=body.source_url,
            )
        except database.seasons.SeasonError as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        return season
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.post(
    '/{olympiad_id}/seasons/{season_id}/archive',
    response_model=schemas.seasons.SeasonItem,
    responses={
        200: {'description': 'Сезон перенесён в архив'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Season not found'},
        500: {'description': 'Internal server error'},
    },
)
async def archive_season(
    olympiad_id: uuid.UUID,
    season_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Перенести сезон в архив (пометить завершённым)."""
    try:
        season = await database.seasons.archive_season(season_id)
        if not season or str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(status_code=404, detail='Season not found')
        await audit.audit(
            'season_archive',
            actor_id=current_user.get('id'),
            target_type='olympiad_season',
            target_id=season_id,
        )
        return season
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.post(
    '/{olympiad_id}/seasons/{season_id}/profiles',
    response_model=schemas.seasons.ProfileItem,
    status_code=201,
    responses={
        201: {'description': 'Профиль добавлен'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Season not found'},
        409: {'description': 'Профиль с таким названием уже есть'},
        500: {'description': 'Internal server error'},
    },
)
async def add_season_profile(
    olympiad_id: uuid.UUID,
    season_id: uuid.UUID,
    body: schemas.seasons.ProfileCreate,
    current_user: deps.AdminUser = None,
):
    """Добавить профиль в сезон (администратор)."""
    try:
        season = await database.seasons.get_season(season_id)
        if not season or str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(status_code=404, detail='Season not found')
        profile = await database.seasons.add_profile(
            season_id,
            name=body.name,
            subject=body.subject,
            description=body.description,
        )
        if profile is None:
            raise HTTPException(
                status_code=409,
                detail='Профиль с таким названием уже есть в этом сезоне',
            )
        return profile
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.put(
    '/{olympiad_id}/seasons/{season_id}/profiles/{profile_id}',
    response_model=schemas.seasons.ProfileItem,
    responses={
        200: {'description': 'Профиль обновлён'},
        400: {'description': 'Пустое название'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Season or profile not found'},
        409: {'description': 'Профиль с таким названием уже есть'},
        500: {'description': 'Internal server error'},
    },
)
async def edit_season_profile(
    olympiad_id: uuid.UUID,
    season_id: uuid.UUID,
    profile_id: uuid.UUID,
    body: schemas.seasons.ProfileUpdate,
    current_user: deps.AdminUser = None,
):
    """Изменить профиль сезона (администратор)."""
    try:
        season = await database.seasons.get_season(season_id)
        if not season or str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(status_code=404, detail='Season not found')
        try:
            profile = await database.seasons.edit_profile(
                season_id,
                profile_id,
                **body.model_dump(exclude_unset=True),
            )
        except database.seasons.SeasonError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if profile is None:
            raise HTTPException(status_code=404, detail='Profile not found')
        return profile
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.delete(
    '/{olympiad_id}/seasons/{season_id}/profiles/{profile_id}',
    status_code=204,
    responses={
        204: {'description': 'Профиль удалён'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Season or profile not found'},
        409: {'description': 'Профиль используется в правилах льгот'},
        500: {'description': 'Internal server error'},
    },
)
async def delete_season_profile(
    olympiad_id: uuid.UUID,
    season_id: uuid.UUID,
    profile_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Удалить профиль сезона, если на него не ссылаются правила льгот."""
    try:
        season = await database.seasons.get_season(season_id)
        if not season or str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(status_code=404, detail='Season not found')
        try:
            removed = await database.seasons.remove_profile(season_id, profile_id)
        except database.seasons.SeasonError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if not removed:
            raise HTTPException(status_code=404, detail='Profile not found')
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.post(
    '/add_olympiad',
    response_model=schemas.olympiads.OlympiadResponse,
    status_code=201,
    responses={
        201: {'description': 'Olympiad created'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        409: {'description': 'Olympiad with this name already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def add_olympiad(
    olympiad: schemas.olympiads.OlympiadCreate,
    current_user: deps.AdminUser = None,
):
    """Создать олимпиаду вручную (администратором).

    Резервный способ: основной путь наполнения каталога — импорт РСОШ.
    """
    try:
        created = await database.olympiads.add_olympiad(olympiad.model_dump())
        if not created:
            raise HTTPException(
                status_code=409,
                detail='Olympiad with this name already exists',
            )
        return created
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.post(
    '/edit_olympiad/{olympiad_id}',
    response_model=schemas.olympiads.OlympiadResponse,
    responses={
        200: {'description': 'Olympiad updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Olympiad not found'},
        409: {'description': 'Olympiad with this name already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def edit_olympiad(
    olympiad_id: uuid.UUID,
    olympiad: schemas.olympiads.OlympiadUpdate,
    current_user: deps.AdminUser = None,
):
    """Изменить олимпиаду (администратором)."""
    try:
        update_data = olympiad.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')
        updated = await database.olympiads.edit_olympiad(olympiad_id, update_data)
        if not updated:
            existing = await database.olympiads.get_olympiad(olympiad_id)
            if not existing:
                raise HTTPException(status_code=404, detail='Olympiad not found')
            raise HTTPException(
                status_code=409,
                detail='Olympiad with this name already exists',
            )
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
