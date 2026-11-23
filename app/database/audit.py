import logging

import uuid as uuid_mod
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.users import Users

logger = logging.getLogger('papaya.audit')


def _as_uuid(value):
    """UUID или ``None``.

    Аудит — вторичная запись: идентификатор нестандартного типа (например,
    строка-метка сезона) не должен терять всю запись. Невалидное значение
    сохраняем как ``None``, а исходник остаётся в ``before``/``after``.
    """
    if value is None:
        return None
    if isinstance(value, uuid_mod.UUID):
        return value
    try:
        return uuid_mod.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _jsonable(value):
    """Привести снимок к JSONB-совместимому виду.

    ``log_action`` вызывается из разных слоёв: туда попадают ORM-объекты,
    ``datetime``, ``Decimal`` и UUID. Без преобразования PostgreSQL отклоняет
    вставку, а вместе с ней теряется и сам факт действия.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid_mod.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value)


async def log_action(entity_type, entity_id=None, action='', user_id=None, before=None, after=None, request_id=None):
    try:
        async with AsyncSessionLocal() as session:
            row = AuditLog(
                entity_type=entity_type,
                entity_id=_as_uuid(entity_id),
                action=action,
                user_id=_as_uuid(user_id),
                before=_jsonable(before),
                after=_jsonable(after),
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
            select(AuditLog, Users).outerjoin(Users, Users.id == AuditLog.user_id),
            entity_type, entity_id, action,
        )
        stmt = (
            stmt.order_by(AuditLog.createdAt.desc(), AuditLog.id)
            .limit(limit)
            .offset(max(0, int(offset or 0)))
        )
        result = await session.execute(stmt)
        return [_audit_to_dict(row, user) for row, user in result.all()]


def _apply_audit_filters(stmt, entity_type=None, entity_id=None, action=None):
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == _as_uuid(entity_id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return stmt


def _audit_to_dict(r, user=None):
    return {
        'id': str(r.id),
        'entity_type': r.entity_type,
        'entity_id': str(r.entity_id) if r.entity_id else None,
        'action': r.action,
        'user_id': str(r.user_id) if r.user_id else None,
        'user_name': ' '.join(
            part for part in (
                getattr(user, 'name', None),
                getattr(user, 'surname', None),
            ) if part
        ) or None,
        'user_email': getattr(user, 'email', None),
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