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

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import database, schemas
from app.core import deps

olympiads_page = APIRouter(
    prefix='/olympiads',
    tags=['olympiads'],
)

logger = logging.getLogger('papaya.olympiads')


class OlympiadListItem(BaseModel):
    """Публичная строка каталога олимпиад.

    Состав — как у публичной карточки: пользовательские поля и ``status``.
    ``archive_reason`` (``RSOSH_ABSENT`` / ``MANUAL``) — технические значения
    для панели администратора, посетителю они ничего не объясняют; архив он
    видит по ``status``.
    """

    id: str | None = None
    name: str | None = None
    description: str | None = None
    official_url: str | None = None
    preview_image: str | None = None
    image: str | None = None
    source_url: str | None = None
    status: str | None = None
    is_archived: bool = False


class OlympiadsResponse(BaseModel):
    olympiads: List[OlympiadListItem]


#: Заголовок источника для олимпиады, созданной вручную. Такой записи нет в
#: перечне РСОШ, и это нужно сказать прямо, а не молча показать пустоту.
MANUAL_SOURCE_TITLE = 'Создано администратором Papaya'

#: Заголовок источника для записи из документа РСОШ, у которого нет названия.
RSOSH_SOURCE_TITLE = 'Перечень олимпиад РСОШ'


class SourceInfo(BaseModel):
    """Откуда взялась информация об олимпиаде.

    Ровно два поля, оба пользовательские: ``title`` — что стало источником
    данных, ``source_url`` — публичная ссылка, если она есть. Внутренние
    детали документа (UUID, имя файла, хеш, статус обработки, metadata) здесь
    не отдаются: ответ на вопрос «откуда это» не должен быть доступом к
    загруженному файлу.
    """

    title: str | None = None
    source_url: str | None = None


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
        'preview_image': olympiad.get('preview_image'),
        'image': olympiad.get('image'),
        'source_url': olympiad.get('source_url'),
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
):
    """Каталог олимпиад — публичное чтение без авторизации."""
    try:
        olympiads = await database.olympiads.list_olympiads(
            status=None if include_archived else 'PUBLISHED',
            search=search,
            limit=limit,
        )
        return {'olympiads': [_serialize(item) for item in olympiads]}
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
    источника — документ РСОШ и ручной ввод администратора, и оба надо называть
    прямо. Раньше «нет документа» грозил ошибкой, из-за чего ручная олимпиада
    выглядела сломанной.

    - импорт РСОШ → ``title`` из названия документа, ``source_url`` из metadata
      или из поля олимпиады;
    - ручное создание → ``title`` = «Создано администратором Papaya»,
      ``source_url`` = заполненная ссылка или ``null``.

    Название файла, хеш, статус обработки и прочие служебные поля документа
    наружу не отдаются: нужен ответ на вопрос «откуда это», а не доступ к
    загруженному файлу.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')

        title = MANUAL_SOURCE_TITLE
        source_url = olympiad.get('source_url') or None

        doc_id = olympiad.get('source_doc_id')
        if doc_id:
            doc = await database.docs.get_doc(uuid.UUID(str(doc_id)))
            if doc:
                metadata = doc.get('metadata') or {}
                rsosh = metadata.get('rsosh') or {}
                title = metadata.get('title') or rsosh.get('title') or RSOSH_SOURCE_TITLE
                source_url = metadata.get('source_url') or source_url

        return SourceInfo(title=title, source_url=source_url)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiads_page.get(
    '/{olympiad_id}/universities',
    response_model=schemas.bvi.BviUniversitiesResponse,
    responses={
        200: {'description': 'Университеты, дающие БВИ за эту олимпиаду'},
        404: {'description': 'Olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def olympiad_universities(olympiad_id: uuid.UUID):
    """Университеты, дающие БВИ за олимпиаду (обратная сторона связи).

    Публично видны только подтверждённые связи: заявка, ещё не одобренная
    администратором, публичным фактом не является.

    Если олимпиада архивная, связи остаются в списке, но помечаются
    ``is_historical``: университеты действительно давали БВИ, пока олимпиада
    была в перечне РСОШ. Удалять их из-за архива нельзя — это стёрло бы
    историю, и страница олимпиады выглядела бы «пустой», хотя информация о
    льготе была.
    """
    try:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        universities = await database.bvi.list_universities_for_olympiad(olympiad_id)
        return {'universities': universities}
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
