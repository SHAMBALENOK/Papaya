import uuid as uuid_mod
from datetime import datetime, timezone
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.representative import RepresentativeApplication
from app.models.universities import Universities
from app.models.users import Users

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))

def _iso(v):
    return v.isoformat() if v else None

def app_to_dict(a, user=None, university=None):
    return {
        'id': str(a.id),
        'user_id': str(a.user_id),
        'university_id': str(a.university_id),
        'user_name': ' '.join(
            part for part in (
                getattr(user, 'name', None),
                getattr(user, 'surname', None),
            ) if part
        ) or None,
        'user_email': getattr(user, 'email', None),
        'university_name': (
            getattr(university, 'short_name', None)
            or getattr(university, 'name', None)
        ),
        'justification': a.justification,
        'status': a.status,
        'reviewed_by': str(a.reviewed_by) if a.reviewed_by else None,
        'reviewed_at': _iso(a.reviewed_at),
        'rejection_reason': a.rejection_reason,
        'createdAt': _iso(a.createdAt),
        'updatedAt': _iso(a.updatedAt),
    }

async def create_application(user_id, university_id, justification=None):
    async with AsyncSessionLocal() as session:
        # Повторная отправка той же заявки не создаёт дубль: пользователь
        # видит уже существующую заявку «на рассмотрении», а админ — одну
        # строку вместо очереди одинаковых.
        existing = (await session.execute(
            select(RepresentativeApplication).where(
                RepresentativeApplication.user_id == _as_uuid(user_id),
                RepresentativeApplication.university_id == _as_uuid(university_id),
                RepresentativeApplication.status == 'pending',
            )
        )).scalars().first()
        if existing:
            return app_to_dict(existing)
        a = RepresentativeApplication(
            user_id=_as_uuid(user_id),
            university_id=_as_uuid(university_id),
            justification=justification,
        )
        session.add(a)
        await session.commit()
        await session.refresh(a)
        return app_to_dict(a)

async def list_applications(status=None, user_id=None):
    async with AsyncSessionLocal() as session:
        stmt = (
            select(RepresentativeApplication, Users, Universities)
            .outerjoin(Users, Users.id == RepresentativeApplication.user_id)
            .outerjoin(
                Universities,
                Universities.id == RepresentativeApplication.university_id,
            )
        )
        if status:
            stmt = stmt.where(RepresentativeApplication.status == status)
        if user_id:
            stmt = stmt.where(
                RepresentativeApplication.user_id == _as_uuid(user_id)
            )
        stmt = stmt.order_by(RepresentativeApplication.createdAt.desc())
        rows = (await session.execute(stmt)).all()
        return [app_to_dict(a, user, university) for a, user, university in rows]

async def get_application(app_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(RepresentativeApplication).where(RepresentativeApplication.id == _as_uuid(app_id)))
        a = result.scalar_one_or_none()
        return app_to_dict(a) if a else None

async def review_application(app_id, status, reviewer_id, rejection_reason=None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(RepresentativeApplication).where(RepresentativeApplication.id == _as_uuid(app_id)))
        a = result.scalar_one_or_none()
        if not a:
            return None
        a.status = status
        a.reviewed_by = _as_uuid(reviewer_id)
        a.reviewed_at = datetime.now(timezone.utc)
        a.rejection_reason = rejection_reason
        await session.commit()
        await session.refresh(a)
        return app_to_dict(a)