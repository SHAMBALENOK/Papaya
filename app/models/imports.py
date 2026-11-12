"""История запусков импорта.

Состояние конкретного прогона по-прежнему живёт в ``docs.metadata['rsosh']``
(это совместимо с текущим импортёром), но каждый запуск дополнительно
фиксируется в ``import_jobs``: кто запустил, когда, чем закончилось.
``import_records`` хранит построчный результат подтверждения.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportJob(Base):
    __tablename__ = 'import_jobs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    kind = Column(String, nullable=False, default='RSOSH', index=True)
    status = Column(String, nullable=False, default='PROCESSING', index=True)
    started_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    started_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    summary = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    records = relationship(
        'ImportRecord',
        back_populates='job',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )


class ImportRecord(Base):
    __tablename__ = 'import_records'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey('import_jobs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=True)
    action = Column(String, nullable=True)
    status = Column(String, nullable=True)
    payload = Column(JSONB, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)

    job = relationship('ImportJob', back_populates='records')
