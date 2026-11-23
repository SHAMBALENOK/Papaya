"""Слой заявок на роль администратора Papaya."""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.admin_applications import AdminApplication
from app.models.users import Users


def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _iso(value):
    return value.isoformat() if value else None


def application_to_dict(application, user=None):
    return {
        'id': str(application.id),
        'user_id': str(application.user_id),
        'user_name': ' '.join(
            part for part in (
                getattr(user, 'name', None),
                getattr(user, 'surname', None),
            ) if part
        ) or None,
        'user_email': getattr(user, 'email', None),
        'contact_email': application.contact_email,
        'motivation': application.motivation,
        'status': application.status,
        'reviewed_by': (
            str(application.reviewed_by) if application.reviewed_by else None
        ),
        'reviewed_at': _iso(application.reviewed_at),
        'rejection_reason': application.rejection_reason,
        'createdAt': _iso(application.createdAt),
        'updatedAt': _iso(application.updatedAt),
    }


async def get_application(application_id):
    async with AsyncSessionLocal() as session:
        row = await session.get(AdminApplication, _as_uuid(application_id))
        if row is None:
            return None
        user = await session.get(Users, row.user_id)
        return application_to_dict(row, user)


async def create_application(user_id, contact_email, motivation):
    """Создать заявку; повторная отправка возвращает уже существующую pending."""
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(AdminApplication).where(
                    AdminApplication.user_id == _as_uuid(user_id),
                    AdminApplication.status == 'pending',
                )
            )
        ).scalars().first()
        if existing is not None:
            return application_to_dict(existing)
        application = AdminApplication(
            user_id=_as_uuid(user_id),
            contact_email=contact_email,
            motivation=motivation,
        )
        session.add(application)
        await session.commit()
        await session.refresh(application)
        return application_to_dict(application)


async def list_applications(status=None, user_id=None):
    async with AsyncSessionLocal() as session:
        stmt = (
            select(AdminApplication, Users)
            .outerjoin(Users, Users.id == AdminApplication.user_id)
            .order_by(AdminApplication.createdAt.desc())
        )
        if status:
            stmt = stmt.where(AdminApplication.status == status)
        if user_id:
            stmt = stmt.where(AdminApplication.user_id == _as_uuid(user_id))
        rows = (await session.execute(stmt)).all()
        return [
            application_to_dict(application, user)
            for application, user in rows
        ]


async def review_application(
    application_id, status, reviewer_id, rejection_reason=None
):
    """Закрыть заявку. Возвращает ``None``, если её нет или она уже закрыта."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(AdminApplication)
                .where(AdminApplication.id == _as_uuid(application_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None or row.status != 'pending':
            return None
        row.status = status
        row.reviewed_by = _as_uuid(reviewer_id)
        row.reviewed_at = datetime.now(timezone.utc)
        row.rejection_reason = rejection_reason
        await session.commit()
        await session.refresh(row)
        user = await session.get(Users, row.user_id)
        return application_to_dict(row, user)
