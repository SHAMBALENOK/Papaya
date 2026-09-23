import uuid
from datetime import datetime, timezone
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import DateTime, Column, String, Text


class Organizations(Base):
    """Организация Papaya — источник истины об организациях.

    Тип организации задаётся строковым enum-значением из:
    UNIVERSITY, ORGANIZER, SCHOOL, OTHER.

    Отдельные таблицы под университеты/организаторов/школы не создаются:
    специфичные данные, не требующие собственной сущности, хранятся в
    ``metadata`` (DB-колонка ``metadata``).

    Два практически важных класса организации:
      - организаторы олимпиад (олимпиада ссылается на них массивом ID
        ``olympiads.organizer_ids`` в JSONB);
      - университеты, предоставляющие БВИ (``olympiads.bvi_organizations``).
    Организация может принадлежать обоим классам одновременно.
    """

    __tablename__ = 'organizations'

    ORGANIZATION_TYPES = ('UNIVERSITY', 'ORGANIZER', 'SCHOOL', 'OTHER')

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    short_name = Column(String, nullable=True)
    type = Column(String, nullable=False, default='OTHER')
    description = Column(Text, nullable=True)
    website = Column(String, nullable=True)
    logo = Column(String, nullable=True)
    contacts = Column(JSONB, nullable=True)
    metadata_ = Column('metadata', JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )