"""Слой доступа к документам-источникам Papaya.

Документ — источник данных, а не пользовательский объект: по нему видно,
откуда взялась информация об олимпиадах, и его же использует импорт РСОШ
(``app/rsosh`` хранит состояние прогона в ``docs.metadata['rsosh']``).
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.database.search import comparable_text_sql, like_pattern
from app.middlewares.serializers import doc_to_dict
from app.models.docs import Docs


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def get_doc(doc_id) -> dict | None:
    """Найти документ по id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Docs).where(Docs.id == _as_uuid(doc_id))
        )
        doc = result.scalar_one_or_none()
        return doc_to_dict(doc) if doc else None


async def list_docs(
    *,
    doc_type: str | None = None,
    status: str | None = None,
    university_id=None,
    uploaded_by=None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Детерминированный список документов с необязательными фильтрами."""
    statement = _apply_doc_filters(
        select(Docs),
        doc_type=doc_type,
        status=status,
        university_id=university_id,
        uploaded_by=uploaded_by,
        search=search,
    )
    statement = statement.order_by(Docs.createdAt.desc(), Docs.id)
    if limit is not None:
        statement = statement.limit(limit).offset(max(0, int(offset or 0)))

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [doc_to_dict(doc) for doc in result.scalars().all()]


def _apply_doc_filters(
    statement,
    *,
    doc_type=None,
    status=None,
    university_id=None,
    uploaded_by=None,
    search=None,
):
    if doc_type is not None:
        statement = statement.where(Docs.type == doc_type)
    if status is not None:
        statement = statement.where(Docs.status == status)
    if university_id is not None:
        statement = statement.where(Docs.university_id == _as_uuid(university_id))
    if uploaded_by is not None:
        statement = statement.where(Docs.uploaded_by == _as_uuid(uploaded_by))
    query = (search or '').strip()
    if query:
        statement = statement.where(
            comparable_text_sql(Docs.name).ilike(like_pattern(query), escape='\\')
        )
    return statement


async def count_docs(
    *,
    doc_type: str | None = None,
    status: str | None = None,
    university_id=None,
    uploaded_by=None,
    search: str | None = None,
) -> int:
    statement = _apply_doc_filters(
        select(func.count()).select_from(Docs),
        doc_type=doc_type,
        status=status,
        university_id=university_id,
        uploaded_by=uploaded_by,
        search=search,
    )
    async with AsyncSessionLocal() as session:
        return int((await session.execute(statement)).scalar_one())


async def add_doc(ins: dict) -> dict | None:
    """Создать документ.

    ``ins['id']`` опционален: при загрузке файла id вычисляется заранее,
    чтобы ``storage_key`` строился от id документа.
    """
    values = {
        'name': ins.get('name'),
        'type': ins.get('type') or 'RSOSH_LIST',
        'storage_key': ins.get('storage_key'),
        'mime_type': ins.get('mime_type'),
        'source_url': ins.get('source_url'),
        'checksum': ins.get('checksum'),
        'status': ins.get('status') or 'UPLOADED',
        'metadata': ins.get('metadata'),
        'note': ins.get('note'),
        'university_id': _as_uuid(ins['university_id']) if ins.get('university_id') else None,
        'uploaded_by': _as_uuid(ins['uploaded_by']) if ins.get('uploaded_by') else None,
    }
    if ins.get('id'):
        values['id'] = _as_uuid(ins['id'])

    now = datetime.now(timezone.utc)
    doc = Docs(createdAt=now, updatedAt=now, **values)
    async with AsyncSessionLocal() as session:
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc_to_dict(doc)


_DOC_EDITABLE_FIELDS = frozenset({
    'name', 'type', 'status', 'source_url', 'note', 'metadata', 'university_id',
})

# В API и в слое доступа раздел состояния импорта называется ``metadata``
# (так он лежит в JSONB-колонке ``docs.metadata``), а атрибут модели — ``meta``:
# имя ``metadata`` зарезервировано Declarative API. Маппинг не даёт записать
# «метаданные» в обычный Python-атрибут и потерять раздел импорта.
_DOC_FIELD_ATTRIBUTES = {'metadata': 'meta'}


async def edit_doc(doc_id, ins: dict) -> dict | None:
    """Изменить документ (в т.ч. состояние импорта и раздел ``metadata``)."""
    doc_uuid = _as_uuid(doc_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Docs).where(Docs.id == doc_uuid)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        for key, value in ins.items():
            if key in _DOC_EDITABLE_FIELDS:
                attr = _DOC_FIELD_ATTRIBUTES.get(key, key)
                if key == 'university_id' and value is not None:
                    value = _as_uuid(value)
                setattr(doc, attr, value)
        doc.updatedAt = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(doc)
        return doc_to_dict(doc)
