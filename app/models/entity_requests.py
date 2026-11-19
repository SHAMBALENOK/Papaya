"""Запросы на добавление отсутствующих сущностей каталога.

Представитель университета не создаёт олимпиады, сезоны и профили напрямую:
он описывает, чего не хватает, а администратор проверяет запрос и создаёт
сущность. Так каталог не расползается на дубли и придуманные олимпиады.

Запрос всегда привязан к вузу (кто просит) и, для сезона/профиля, к родителю:
сезон — к олимпиаде, профиль — к сезону. Привязка хранится в ``parent_id``
без внешнего ключа: родитель зависит от ``entity_type``, а проверка
принадлежности выполняется в слое данных.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


ENTITY_TYPES = ('OLYMPIAD', 'SEASON', 'PROFILE')
REQUEST_STATUSES = ('pending', 'approved', 'rejected')


class EntityRequest(Base):
    __tablename__ = 'entity_requests'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    #: Дополнительные поля будущей сущности (уровень РСОШ, даты, предмет).
    payload = Column(JSONB, nullable=True)
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    parent_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    status = Column(String, nullable=False, default='pending', index=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    #: id созданной сущности — чтобы запрос и результат были связаны.
    created_entity_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
