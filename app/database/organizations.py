import uuid as uuid_mod

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import organization_to_dict
from app.models.organizations import Organizations


async def get_organization(org_id: str) -> dict | None:
    """Найти организацию по id."""
    if isinstance(org_id, str):
        org_id = uuid_mod.UUID(org_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Organizations).where(Organizations.id == org_id)
        )
        org = result.scalar_one_or_none()
        return organization_to_dict(org) if org else None


async def list_organizations(
    *,
    org_type: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Детерминированный список организаций, при необходимости по типу."""
    statement = select(Organizations)
    if org_type is not None:
        statement = statement.where(Organizations.type == org_type)
    statement = statement.order_by(Organizations.created_at.desc(), Organizations.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [organization_to_dict(org) for org in result.scalars().all()]


# Поля, которые разрешено менять через edit_organization. Управление
# временными метками и id целиком на стороне сервера.
_ORG_EDITABLE_FIELDS = frozenset({
    'name', 'short_name', 'type', 'description', 'website',
    'logo', 'contacts', 'metadata',
})


async def add_organization(ins: dict) -> dict:
    """Создать организацию."""
    org = Organizations(
        name=ins.get('name'),
        short_name=ins.get('short_name'),
        type=ins.get('type', 'OTHER'),
        description=ins.get('description'),
        website=ins.get('website'),
        logo=ins.get('logo'),
        contacts=ins.get('contacts'),
        metadata_=ins.get('metadata'),
    )
    async with AsyncSessionLocal() as session:
        session.add(org)
        await session.commit()
        await session.refresh(org)
        return organization_to_dict(org)


async def edit_organization(org_id: str, ins: dict) -> dict | None:
    """Изменить организацию.

    Применяются только поля из allowlist ``_ORG_EDITABLE_FIELDS``; всё
    остальное игнорируется. ``updated_at`` перезаписывается сервером.
    """
    if isinstance(org_id, str):
        org_id = uuid_mod.UUID(org_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Organizations).where(Organizations.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            return None
        for key, value in ins.items():
            if key in _ORG_EDITABLE_FIELDS:
                if key == 'metadata':
                    org.metadata_ = value
                else:
                    setattr(org, key, value)
        await session.commit()
        await session.refresh(org)
        return organization_to_dict(org)


async def delete_organization(org_id: str) -> bool:
    """Удалить организацию и разорвать привязку пользователей к ней.

    Ссылки из ``olympiads.organizer_ids`` / ``olympiads.bvi_organizations``
    представляют собой исторические JSONB-значения и сознательно не
    переписываются при удалении.
    """
    from app.models.users import Users

    if isinstance(org_id, str):
        org_id = uuid_mod.UUID(org_id)
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Organizations).where(Organizations.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            return False
        await session.execute(
            update(Users)
            .where(Users.organization_id == org_id)
            .values(organization_id=None)
        )
        await session.delete(org)
        await session.commit()
        return True