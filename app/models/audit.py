import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    """Персистентный журнал критических административных событий (ТЗ §10).

    Строка лога (``papaya.audit``) остаётся, но лог ротируется и теряется, а
    ответ на вопрос «кто выдал администратора / проверил правило / подтвердил
    импорт и когда» нужен спустя месяцы — поэтому событие пишется ещё и в БД.

    ``details`` — произвольный JSON с контекстом события (старое/новое
    значение, причина, номер версии). Журнал только дописывается: маршрутов
    изменения и удаления событий нет.
    """

    __tablename__ = 'audit_events'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(String, nullable=False, index=True)
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True, index=True)
    details = Column(JSONB, nullable=True)
    ip = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
