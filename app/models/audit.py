import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    before = Column(JSONB, nullable=True)
    after = Column(JSONB, nullable=True)
    request_id = Column(String, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)