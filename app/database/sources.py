"""Слой доступа к источникам данных.

Источник — смысловая ссылка на документ или страницу, из которой взято
правило льготы. В отличие от ``Docs`` (загруженный файл), источник может быть
внешним URL и переиспользоваться несколькими правилами.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.models.sources import Source


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _iso(value):
    return value.isoformat() if value else None


def source_to_dict(source: Source) -> dict:
    return {
        'id': str(source.id),
        'name': source.name,
        'url': source.url,
        'kind': source.kind,
        'university_id': str(source.university_id) if source.university_id else None,
        'doc_id': str(source.doc_id) if source.doc_id else None,
        'note': source.note,
        'createdAt': _iso(source.createdAt),
        'updatedAt': _iso(source.updatedAt),
    }


async def get_source(source_id) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source).where(Source.id == _as_uuid(source_id))
        )
        source = result.scalar_one_or_none()
        return source_to_dict(source) if source else None


async def list_sources(
    *,
    university_id=None,
    kind=None,
    include_global=False,
    limit=None,
    offset=0,
):
    async with AsyncSessionLocal() as session:
        stmt = select(Source).order_by(Source.createdAt.desc(), Source.id)
        if university_id:
            university_uuid = _as_uuid(university_id)
            if include_global:
                # Источник может быть общим (например, перечень РСОШ) или
                # принадлежать конкретному вузу. Представителю нужны оба вида.
                stmt = stmt.where(
                    (Source.university_id == university_uuid)
                    | (Source.university_id.is_(None))
                )
            else:
                stmt = stmt.where(Source.university_id == university_uuid)
        if kind:
            stmt = stmt.where(Source.kind == kind)
        if limit is not None:
            stmt = stmt.limit(limit).offset(max(0, int(offset or 0)))
        result = await session.execute(stmt)
        return [source_to_dict(x) for x in result.scalars().all()]


async def count_sources(*, university_id=None, kind=None) -> int:
    async with AsyncSessionLocal() as session:
        stmt = select(func.count()).select_from(Source)
        if university_id:
            stmt = stmt.where(Source.university_id == _as_uuid(university_id))
        if kind:
            stmt = stmt.where(Source.kind == kind)
        return int((await session.execute(stmt)).scalar_one())


async def create_source(data: dict, user_id=None) -> dict:
    async with AsyncSessionLocal() as session:
        source = Source(
            name=data['name'],
            url=data.get('url'),
            kind=data.get('kind') or 'OTHER',
            university_id=(
                _as_uuid(data['university_id'])
                if data.get('university_id')
                else None
            ),
            doc_id=_as_uuid(data['doc_id']) if data.get('doc_id') else None,
            note=data.get('note'),
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc),
        )
        session.add(source)
        await session.commit()
        # После commit атрибуты истекают: без refresh обращение к ним в
        # async-сессии потребовало бы IO вне await и упало бы MissingGreenlet.
        await session.refresh(source)
        return source_to_dict(source)


async def delete_source(source_id) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source).where(Source.id == _as_uuid(source_id))
        )
        source = result.scalar_one_or_none()
        if not source:
            return False
        await session.delete(source)
        await session.commit()
        return True
