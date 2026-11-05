import uuid as uuid_mod
from datetime import datetime, timezone
from sqlalchemy import select

from app.database.database import AsyncSessionLocal

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else (uuid_mod.UUID(str(value)) if value else None)

async def log_action(entity_type, entity_id=None, action='', user_id=None, before=None, after=None, request_id=None):
    try:
        from app.models.audit import AuditLog
        async with AsyncSessionLocal() as session:
            row = AuditLog(
                entity_type=entity_type,
                entity_id=_as_uuid(entity_id),
                action=action,
                user_id=_as_uuid(user_id),
                before=before,
                after=after,
                request_id=request_id,
                createdAt=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
    except Exception:
        pass

async def list_audit(entity_type=None, entity_id=None, limit=100):
    from app.models.audit import AuditLog
    async with AsyncSessionLocal() as session:
        stmt = select(AuditLog)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(AuditLog.entity_id == _as_uuid(entity_id))
        stmt = stmt.order_by(AuditLog.createdAt.desc()).limit(limit)
        result = await session.execute(stmt)
        return [
            {
                'id': str(r.id),
                'entity_type': r.entity_type,
                'entity_id': str(r.entity_id) if r.entity_id else None,
                'action': r.action,
                'user_id': str(r.user_id) if r.user_id else None,
                'before': r.before,
                'after': r.after,
                'request_id': r.request_id,
                'createdAt': r.createdAt.isoformat() if r.createdAt else None,
            }
            for r in result.scalars().all()
        ]