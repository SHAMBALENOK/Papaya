"""Архив значений, удалённых при переходе на новую модель.

Таблицы ``university_olympiads``, ``sources`` и поля сезонов удаляются сразу
после переноса данных. Всё, что не удалось преобразовать в новую модель
однозначно, остаётся здесь сырым JSON: исходная информация не теряется, но и
не притворяется действующими данными каталога.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MigrationArchive(Base):
    __tablename__ = 'migration_archive'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    field = Column(String, nullable=True)
    old_value = Column(JSONB, nullable=True)
    note = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
