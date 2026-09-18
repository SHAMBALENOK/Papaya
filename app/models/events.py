import uuid
from datetime import datetime, timezone
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, Column, String, Boolean


class Events(Base):
    """Событие (олимпиада или иное мероприятие) на платформе.

    Поле owner — UUID создателя события. Исторически owner не объявлен как
    внешний ключ на users.id (миграция не добавляется намеренно: схема уже
    существует на production-данных), возможная связь добавляется будущими
    миграциями.
    """

    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Индекс по владельцу ускоряет выборку «мои события» и админ-список.
    owner = Column(UUID(as_uuid=True), index=True)
    name = Column(String)
    disc = Column(String, nullable=True)
    preview_picture = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    isActive = Column(Boolean, default=True)
    # Индекс ускоряет сортировку списков событий по дате создания.
    createdAt = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updatedAt = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))