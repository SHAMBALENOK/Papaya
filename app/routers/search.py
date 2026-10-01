"""Поиск по каталогам Papaya.

Основной сценарий Papaya начинается с поиска университета:

    поиск → университет → БВИ-олимпиады → олимпиада → сайт олимпиады

Поэтому поиск один и отдаёт оба типа сущностей сразу: школьнику не нужно
угадывать, в каком разделе искать — «Высшая проба» может быть и
университетом, и олимпиадой. Фильтры по каталогам (``?search=``) тоже
остаются: страницы каталогов используют их при вводе в поиск.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import database, schemas

search_page = APIRouter(
    prefix='/search',
    tags=['search'],
)

logger = logging.getLogger('papaya.search')

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class SearchResults(BaseModel):
    """Результат поиска по каталогам.

    Элементы — те же публичные схемы, что и в каталогах. Раньше здесь стояли
    ``List[dict]``, и в выдачу попадали сырые записи слоя данных вместе со
    служебными полями (``name_norm``, метки времени, ``source_doc_id``):
    поиск был единственным публичным маршрутом, который их отдавал.
    """

    query: str
    universities: List[schemas.universities.UniversityPublicResponse]
    olympiads: List[schemas.olympiads.OlympiadListItem]


@search_page.get(
    '',
    response_model=SearchResults,
    responses={
        200: {'description': 'Universities and olympiads matching the query'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def search(
    q: str = Query(default='', description='Поисковый запрос'),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """Единый поиск по университетам и олимпиадам (публично, без авторизации).

    Ищет только по двум каталогам: пользователи, документы, заявки БВИ и
    служебные данные в выдачу не попадают — поиск отвечает на вопрос «найти
    университет или олимпиаду», а не «поискать по базе».
    """
    try:
        query = (q or '').strip()
        if not query:
            return {'query': '', 'universities': [], 'olympiads': []}
        universities = await database.universities.list_universities(
            search=query,
            limit=limit,
        )
        olympiads = await database.olympiads.list_olympiads(
            status='PUBLISHED',
            search=query,
            limit=limit,
        )
        # Валидация моделей ещё и отсекает лишнее: сырые словари слоя данных
        # содержат поля, которых нет в публичной модели.
        return {
            'query': query,
            'universities': [
                schemas.universities.UniversityPublicResponse(**item)
                for item in universities
            ],
            'olympiads': [
                schemas.olympiads.OlympiadListItem(
                    id=item.get('id'),
                    name=item.get('name'),
                    description=item.get('description'),
                    official_url=item.get('official_url'),
                    preview_image=item.get('preview_image'),
                    image=item.get('image'),
                    source_url=item.get('source_url'),
                    status=item.get('status') or 'PUBLISHED',
                    is_archived=item.get('status') != 'PUBLISHED',
                )
                for item in olympiads
            ],
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
