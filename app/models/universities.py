import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Universities(Base):
    """Университет — главный объект каталога Papaya.

    Университет отвечает на вопрос школьника «какие олимпиады дают БВИ в
    нужном мне университете», поэтому кроме справочных данных хранит только
    связи с олимпиадами каталога (см. ``app/models/bvi.py``).

    Отдельной сущности «организация» в проекте нет: ни организаторы олимпиад,
    ни школы Papaya сейчас не моделирует, а универсальная организация была бы
    лишним уровнем абстракции для единственного типа участника.

    ``name_norm`` — нормализованное имя (регистр, «ё», лишние пробелы и
    типографские кавычки). Он же держит уникальность каталога: вуз нельзя
    завести дважды, даже если в написании есть мелкие различия.
    """

    __tablename__ = 'universities'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    name_norm = Column(String, nullable=False, unique=True, index=True)
    short_name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    website = Column(String, nullable=True)
    image = Column(String, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    bvi_links = relationship(
        'UniversityBvi',
        back_populates='university',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
