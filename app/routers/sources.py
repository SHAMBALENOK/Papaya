"""Источники данных: смысловые ссылки на документы и страницы.

``Source`` отличается от ``Docs``: документ — это загруженный файл, а источник
может быть внешним URL (перечень РСОШ, приказ на сайте вуза) и использоваться
несколькими правилами льгот. Администратор ведёт справочник источников, а
представитель выбирает подходящий источник в форме правила.

Представителю отдаются общие источники и источники его университета: чужой
приказ в его форме бесполезен, а перечень РСОШ нужен всем.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app import database
from app.core import deps
from app.schemas.urls import ExternalUrl

admin_sources_page = APIRouter(prefix='/admin/sources', tags=['sources'])
university_sources_page = APIRouter(tags=['sources'])

SOURCE_KINDS = ('RSOSH_LIST', 'UNIVERSITY_ORDER', 'WEBSITE', 'OTHER')


class SourceCreate(BaseModel):
    name: str
    url: ExternalUrl = None
    kind: str = 'OTHER'
    university_id: uuid.UUID | None = None
    doc_id: uuid.UUID | None = None
    note: str | None = None

    @field_validator('name')
    @classmethod
    def _name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError('name is required')
        return v.strip()

    @field_validator('kind')
    @classmethod
    def _check_kind(cls, v):
        if v not in SOURCE_KINDS:
            raise ValueError('kind must be one of ' + ', '.join(SOURCE_KINDS))
        return v


async def _validate_refs(body: SourceCreate) -> None:
    if body.university_id:
        university = await database.universities.get_university(body.university_id)
        if not university:
            raise HTTPException(status_code=400, detail='University not found')
    if body.doc_id:
        doc = await database.docs.get_doc(body.doc_id)
        if not doc:
            raise HTTPException(status_code=400, detail='Document not found')


@admin_sources_page.get('')
async def admin_list_sources(
    university_id: uuid.UUID | None = None,
    kind: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    """Справочник источников: общие и вузовские."""
    sources = await database.sources.list_sources(
        university_id=university_id,
        kind=kind,
        limit=limit,
        offset=offset,
    )
    total = await database.sources.count_sources(
        university_id=university_id, kind=kind
    )
    return {'sources': sources, 'total': total}


@admin_sources_page.post('', status_code=201)
async def admin_create_source(
    body: SourceCreate,
    current_user: deps.AdminUser = None,
):
    """Добавить источник в справочник."""
    await _validate_refs(body)
    source = await database.sources.create_source(
        body.model_dump(), user_id=current_user.get('id')
    )
    await database.audit.log_action(
        'source', source['id'], 'create',
        user_id=current_user.get('id'), after=source,
    )
    return source


@admin_sources_page.delete('/{source_id}')
async def admin_delete_source(
    source_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    """Удалить источник.

    Правила, ссылавшиеся на него, не удаляются: внешний ключ обнуляет
    ``source_id`` (``ON DELETE SET NULL``), а документ-основание и ссылка на
    источник у правила остаются.
    """
    source = await database.sources.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail='Source not found')
    deleted = await database.sources.delete_source(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Source not found')
    await database.audit.log_action(
        'source', source_id, 'delete',
        user_id=current_user.get('id'), before=source,
    )
    return {'deleted': True, 'id': str(source_id)}


@university_sources_page.get('/universities/{university_id}/sources')
async def list_university_sources(
    university_id: uuid.UUID,
    current_user: dict = Depends(deps.require_manage_university),
):
    """Источники, доступные представителю: общие и своего университета."""
    sources = await database.sources.list_sources(
        university_id=university_id, include_global=True
    )
    return {'sources': sources}
