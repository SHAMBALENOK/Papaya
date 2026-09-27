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

from app import database

search_page = APIRouter(
    prefix='/search',
    tags=['search'],
)

logger = logging.getLogger('papaya.search')

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class SearchResults(BaseModel):
    query: str
    universities: List[dict]
    olympiads: List[dict]


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
    """Единый поиск по университетам и олимпиадам (публично, без авторизации)."""
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
        return {
            'query': query,
            'universities': universities,
            'olympiads': olympiads,
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
