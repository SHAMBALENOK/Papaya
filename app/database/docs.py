import uuid as uuid_mod

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import doc_to_dict
from app.models.docs import Docs


async def get_doc(doc_id: str) -> dict | None:
    """Найти документ по id."""
    if isinstance(doc_id, str):
        doc_id = uuid_mod.UUID(doc_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Docs).where(Docs.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        return doc_to_dict(doc) if doc else None


async def list_docs(
    *,
    status: str | None = None,
    doc_type: str | None = None,
    olympiad_id: str | None = None,
    organization_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Детерминированный список документов с опциональными фильтрами."""
    statement = select(Docs)
    if status is not None:
        statement = statement.where(Docs.status == status)
    if doc_type is not None:
        statement = statement.where(Docs.type == doc_type)
    if olympiad_id is not None:
        statement = statement.where(
            Docs.olympiad_id == uuid_mod.UUID(olympiad_id)
        )
    if organization_id is not None:
        statement = statement.where(
            Docs.organization_id == uuid_mod.UUID(organization_id)
        )
    statement = statement.order_by(Docs.created_at.desc(), Docs.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [doc_to_dict(doc) for doc in result.scalars().all()]


# Поля, которые разрешено менять через edit_doc. id, checksum и временные
# метки пересчитывает/задаёт сервер; переходы status управляются отдельно
# (см. импорт-состояния: UPLOADED -> PROCESSING -> PROCESSED/NEEDS_REVIEW/FAILED).
_DOC_EDITABLE_FIELDS = frozenset({
    'name', 'type', 'storage_key', 'mime_type', 'source_url',
    'organization_id', 'olympiad_id', 'uploaded_by', 'checksum',
    'status', 'metadata',
})


async def add_doc(ins: dict) -> dict:
    """Создать документ.

    ``ins['id']`` опционален: при загрузке файла id вычисляется заранее
    (чтобы ``storage_key`` строился от id документа).
    """
    doc = Docs(
        id=_to_uuid(ins.get('id')),
        name=ins.get('name'),
        type=ins.get('type', 'OTHER'),
        storage_key=ins.get('storage_key'),
        mime_type=ins.get('mime_type'),
        source_url=ins.get('source_url'),
        organization_id=_to_uuid(ins.get('organization_id')),
        olympiad_id=_to_uuid(ins.get('olympiad_id')),
        uploaded_by=_to_uuid(ins.get('uploaded_by')),
        checksum=ins.get('checksum'),
        status=ins.get('status', 'UPLOADED'),
        metadata_=ins.get('metadata'),
    )
    async with AsyncSessionLocal() as session:
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc_to_dict(doc)


async def edit_doc(doc_id: str, ins: dict) -> dict | None:
    """Изменить документ.

    Применяются только поля из allowlist ``_DOC_EDITABLE_FIELDS``; всё
    остальное игнорируется. ``updated_at`` перезаписывается сервером.
    """
    if isinstance(doc_id, str):
        doc_id = uuid_mod.UUID(doc_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Docs).where(Docs.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        for key, value in ins.items():
            if key in _DOC_EDITABLE_FIELDS:
                if key == 'metadata':
                    doc.metadata_ = value
                elif key in ('organization_id', 'olympiad_id', 'uploaded_by'):
                    setattr(doc, key, _to_uuid(value))
                else:
                    setattr(doc, key, value)
        await session.commit()
        await session.refresh(doc)
        return doc_to_dict(doc)


async def delete_doc(doc_id: str) -> bool:
    """Удалить запись о документе (файл из хранилища выносится наружу)."""
    if isinstance(doc_id, str):
        doc_id = uuid_mod.UUID(doc_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Docs).where(Docs.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return False
        await session.delete(doc)
        await session.commit()
        return True


def _to_uuid(value):
    """str/None -> uuid.UUID/None; UUID передаётся без изменений."""
    if value is None:
        return None
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(value)