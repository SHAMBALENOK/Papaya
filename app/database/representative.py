import uuid as uuid_mod
from datetime import datetime, timezone
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.representative import RepresentativeApplication

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))

def _iso(v):
    return v.isoformat() if v else None

def app_to_dict(a):
    return {
        'id': str(a.id),
        'user_id': str(a.user_id),
        'university_id': str(a.university_id),
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
        a = RepresentativeApplication(
            user_id=_as_uuid(user_id),
            university_id=_as_uuid(university_id),
            justification=justification,
        )
        session.add(a)
        await session.commit()
        await session.refresh(a)
        return app_to_dict(a)

async def list_applications(status=None):
    async with AsyncSessionLocal() as session:
        stmt = select(RepresentativeApplication)
        if status:
            stmt = stmt.where(RepresentativeApplication.status == status)
        result = await session.execute(stmt)
        return [app_to_dict(x) for x in result.scalars().all()]

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