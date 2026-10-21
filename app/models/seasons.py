import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OlympiadSeason(Base):
    """Сезон олимпиады (ТЗ §4.2, §4.4).

    Олимпиада и сезон — разные сущности: уровень РСОШ, даты и профили относятся
    к конкретному сезону и не переносятся автоматически из прошлого года в
    новый.

    ``state`` — состояние сезона, отдельное от актуальности олимпиады:
    ``upcoming`` / ``active`` / ``completed`` / ``unknown``. Автоматически
    проставлять ``active`` только потому, что сезон самый новый, нельзя.

    ``dates`` — даты регистрации и проведения (свободная структура). Если даты
    не опубликованы, поле пустое, и интерфейс показывает «Даты пока не
    опубликованы» вместе со ссылкой на официальный сайт.
    """

    __tablename__ = 'olympiad_seasons'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    olympiad_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    #: Уровень РСОШ (1/2/3) — сезонная характеристика.
    rsoh_level = Column(String, nullable=True)
    state = Column(String, nullable=False, default='unknown', index=True)
    dates = Column(JSONB, nullable=True)
    description = Column(Text, nullable=True)
    source_url = Column(String, nullable=True)
    source_doc_id = Column(UUID(as_uuid=True), nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    olympiad = relationship('Olympiads', back_populates='seasons')
    profiles = relationship(
        'OlympiadProfile',
        back_populates='season',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='OlympiadProfile.name_norm',
    )


class OlympiadProfile(Base):
    """Профиль внутри конкретного сезона (ТЗ §4.2, §5.2).

    Профиль принадлежит сезону, а не олимпиаде: у одного сезона может быть
    несколько профилей, и один профиль может быть связан с несколькими
    правилами льгот.
    """

    __tablename__ = 'olympiad_profiles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiad_seasons.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    name_norm = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    season = relationship('OlympiadSeason', back_populates='profiles')
