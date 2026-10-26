"""Запросы представителей о пополнении каталога (олимпиада/сезон/профиль).

Представитель не создаёт записи каталога сам, но его просьба не должна
теряться в переписке: запрос фиксируется, администратор видит его в панели
и закрывает с комментарием.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import catalog_request_to_dict
from app.models.catalog_requests import (
    CATALOG_REQUEST_KINDS,
    CATALOG_REQUEST_STATUSES,
    CatalogRequest,
)
from app.models.olympiads import Olympiads
from app.models.universities import Universities
from app.models.users import Users

__all__ = [
    'CATALOG_REQUEST_KINDS',
    'CATALOG_REQUEST_STATUSES',
    'submit_request',
    'list_requests',
    'count_requests',
    'resolve_request',
]


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def submit_request(
    university_id,
    *,
    user_id,
    kind: str,
    text: str,
    olympiad_id=None,
) -> dict:
    request = CatalogRequest(
        university_id=_as_uuid(university_id),
        user_id=_as_uuid(user_id) if user_id else None,
        kind=kind,
        olympiad_id=_as_uuid(olympiad_id) if olympiad_id else None,
        text=text.strip(),
        status='open',
    )
    async with AsyncSessionLocal() as session:
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return catalog_request_to_dict(request)


def _base_select():
    return (
        select(
            CatalogRequest,
            Universities.name,
            Universities.short_name,
            Olympiads.name,
            Users.email,
        )
        .outerjoin(Universities, CatalogRequest.university_id == Universities.id)
        .outerjoin(Olympiads, CatalogRequest.olympiad_id == Olympiads.id)
        .outerjoin(Users, CatalogRequest.user_id == Users.id)
    )


def _apply_filters(statement, *, status=None, university_id=None):
    if status:
        statement = statement.where(CatalogRequest.status == status)
    if university_id is not None:
        statement = statement.where(CatalogRequest.university_id == _as_uuid(university_id))
    return statement


async def list_requests(
    *,
    status: str | None = None,
    university_id=None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    statement = _apply_filters(
        _base_select(), status=status, university_id=university_id
    ).order_by(CatalogRequest.createdAt.desc(), CatalogRequest.id).offset(offset).limit(limit)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(statement)).all()
        return [
            {
                **catalog_request_to_dict(request),
                'university_name': short_name or name,
                'olympiad_name': olympiad_name,
                'user_email': email,
            }
            for request, name, short_name, olympiad_name, email in rows
        ]


async def count_requests(*, status: str | None = None, university_id=None) -> int:
    statement = _apply_filters(
        select(func.count()).select_from(CatalogRequest),
        status=status,
        university_id=university_id,
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


async def resolve_request(request_id, *, status: str, note: str | None, admin_id) -> dict | None:
    """Закрыть запрос (``resolved``/``rejected``) или снова открыть (``open``)."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        request = (
            await session.execute(
                select(CatalogRequest)
                .where(CatalogRequest.id == _as_uuid(request_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if request is None:
            return None
        request.status = status
        request.admin_note = (note or '').strip() or None
        if status == 'open':
            request.resolved_by = None
            request.resolved_at = None
        else:
            request.resolved_by = _as_uuid(admin_id) if admin_id else None
            request.resolved_at = now
        request.updatedAt = now
        await session.commit()
        await session.refresh(request)
        return catalog_request_to_dict(request)
