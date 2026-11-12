import logging

import uuid as uuid_mod
from datetime import datetime, timezone
from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.models.audit import AuditLog

logger = logging.getLogger('papaya.audit')

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else (uuid_mod.UUID(str(value)) if value else None)

async def log_action(entity_type, entity_id=None, action='', user_id=None, before=None, after=None, request_id=None):
    try:
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
        # Аудит не должен ронять основную операцию, но и молча терять запись
        # нельзя: сбой виден в логах и его можно разобрать.
        logger.exception(
            'Failed to write audit log: entity=%s action=%s',
            entity_type,
            action,
        )

async def list_audit(entity_type=None, entity_id=None, action=None, limit=100, offset=0):
    async with AsyncSessionLocal() as session:
        stmt = _apply_audit_filters(
            select(AuditLog), entity_type, entity_id, action
        )
        stmt = (
            stmt.order_by(AuditLog.createdAt.desc(), AuditLog.id)
            .limit(limit)
            .offset(max(0, int(offset or 0)))
        )
        result = await session.execute(stmt)
        return [_audit_to_dict(r) for r in result.scalars().all()]


def _apply_audit_filters(stmt, entity_type=None, entity_id=None, action=None):
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == _as_uuid(entity_id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return stmt


def _audit_to_dict(r):
    return {
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


async def count_audit(entity_type=None, entity_id=None, action=None):
    async with AsyncSessionLocal() as session:
        stmt = _apply_audit_filters(
            select(func.count()).select_from(AuditLog),
            entity_type,
            entity_id,
            action,
        )
        return int((await session.execute(stmt)).scalar_one())