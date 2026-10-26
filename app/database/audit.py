"""Персистентный журнал административных событий (ТЗ §10).

Запись события не должна ломать основное действие: если БД недоступна,
ошибка пишется в лог, а вызывающий получает ``None``. Журнал только
дописывается — маршрутов правки и удаления событий нет.
"""

import logging
import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import audit_event_to_dict
from app.models.audit import AuditEvent
from app.models.users import Users

logger = logging.getLogger('papaya.audit')


def _as_uuid_or_none(value):
    if value in (None, '', 'none'):
        return None
    try:
        return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def record_event(
    action: str,
    *,
    actor_id=None,
    target_type: str | None = None,
    target_id=None,
    details: dict | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> dict | None:
    """Записать событие; при сбое — залогировать и вернуть ``None``."""
    event = AuditEvent(
        action=action,
        actor_id=_as_uuid_or_none(actor_id),
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=_jsonable(details) if details else None,
        ip=ip,
        request_id=request_id,
        createdAt=datetime.now(timezone.utc),
    )
    try:
        async with AsyncSessionLocal() as session:
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return audit_event_to_dict(event)
    except Exception:  # noqa: BLE001 - аудит не должен ронять действие
        logger.exception('audit: failed to persist event %s', action)
        return None


def _apply_filters(statement, *, action=None, actor_id=None, target_id=None):
    if action:
        statement = statement.where(AuditEvent.action == action)
    if actor_id:
        statement = statement.where(AuditEvent.actor_id == _as_uuid_or_none(actor_id))
    if target_id:
        statement = statement.where(AuditEvent.target_id == str(target_id))
    return statement


async def list_events(
    *,
    action: str | None = None,
    actor_id=None,
    target_id=None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """События от новых к старым, с именем и почтой автора (JOIN, не N+1)."""
    statement = (
        select(AuditEvent, Users.email, Users.name, Users.surname)
        .outerjoin(Users, AuditEvent.actor_id == Users.id)
        .order_by(AuditEvent.createdAt.desc(), AuditEvent.id)
        .offset(offset)
        .limit(limit)
    )
    statement = _apply_filters(statement, action=action, actor_id=actor_id, target_id=target_id)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(statement)).all()
        return [
            {
                **audit_event_to_dict(event),
                'actor_email': email,
                'actor_name': ' '.join(part for part in (name, surname) if part) or None,
            }
            for event, email, name, surname in rows
        ]


async def count_events(*, action=None, actor_id=None, target_id=None) -> int:
    statement = _apply_filters(
        select(func.count()).select_from(AuditEvent),
        action=action,
        actor_id=actor_id,
        target_id=target_id,
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()
