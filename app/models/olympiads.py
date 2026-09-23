import uuid
from datetime import datetime, timezone
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import DateTime, Column, String, Text


class Olympiads(Base):
    """Олимпиада — центральная сущность каталога Papaya.

    Доменно-нормализованный наследник исторической таблицы ``events``:
    миграция 0004 переносит данные событий в эту модель, сохраняя оригинал
    в ``metadata.legacy``.

    Сложные структуры РСОШ хранятся без преждевременной нормализации:

    - ``organizer_ids`` — JSONB-массив ID организаций-организаторов;
    - ``bvi_organizations`` — JSONB-массив ID университетов, дающих БВИ
      (БВИ привязано к организации/университету, а не к олимпиаде вообще);
    - ``profiles`` — JSONB-массив профилей РСОШ, каждый профиль описывает
      ``name``, ``subjects``, ``specialty_groups``, ``level`` и пр.;
    - ``subjects`` / ``levels`` / ``years`` — JSONB-массивы строк;
    - ``metadata`` (DB-колонка ``metadata``) — дополнительная гибкая информация
      (изображения, источники-документы, история миграции).
    """

    __tablename__ = 'olympiads'

    # Статусы жизненного цикла олимпиады в каталоге.
    STATUSES = ('DRAFT', 'PUBLISHED', 'ARCHIVED')

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    organizer_ids = Column(JSONB, nullable=False, default=list)
    description = Column(Text, nullable=True)
    subjects = Column(JSONB, nullable=False, default=list)
    levels = Column(JSONB, nullable=False, default=list)
    years = Column(JSONB, nullable=False, default=list)
    profiles = Column(JSONB, nullable=False, default=list)
    bvi_organizations = Column(JSONB, nullable=False, default=list)
    registration_url = Column(String, nullable=True)
    official_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default='PUBLISHED')
    # Индекс по названию ускоряет точный/фильтрованный поиск дубликатов.
    name_norm = Column(String, nullable=True, index=True)
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