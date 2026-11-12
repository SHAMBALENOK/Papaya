"""Источники данных: нормализованная запись о документе/ссылке.

``Docs`` хранит загруженный файл, а ``Source`` — смысловой источник, на
который ссылается правило льготы: приказ вуза, перечень РСОШ, страница на
сайте. Один источник может использоваться несколькими правилами.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = 'sources'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    url = Column(String, nullable=True)
    kind = Column(String, nullable=False, default='OTHER', index=True)
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
    )
    note = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
