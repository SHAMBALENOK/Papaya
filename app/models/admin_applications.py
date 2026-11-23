"""Заявки пользователей на роль администратора Papaya.

Роль ``ADMIN`` — самый широкий уровень доступа, поэтому заявка хранится
отдельно от запросов в каталог: у неё другой жизненный цикл и другое действие
при одобрении (выдача роли, а не создание сущности). Контактная почта и
мотивационное письмо нужны администратору для осознанного решения.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminApplication(Base):
    __tablename__ = 'admin_applications'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    contact_email = Column(String, nullable=False)
    motivation = Column(Text, nullable=False)
    status = Column(String, nullable=False, default='pending', index=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
