"""Сезоны олимпиад и профили сезонов.

Сезон отвечает только на вопрос «в каком году проводилась олимпиада»:
``season_label`` — например, ``2025/2026``. Дат регистрации и проведения, а
также флага доступности в модели нет: это состояние приёмной кампании
университета, а не свойство олимпиады, и в каталоге Papaya оно не хранится.

Профиль принадлежит конкретному сезону. Уровень РСОШ (1, 2, 3) — свойство
профиля сезона, а не олимпиады: в перечень могут входить только отдельные
профили, и в следующем сезоне их набор и уровни меняются. Поэтому уровень
одного сезона никогда не переносится на другой.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Допустимые уровни РСОШ. ``None`` — профиль не входит в перечень.
RSOSH_LEVELS = ('1', '2', '3')


class OlympiadSeason(Base):
    __tablename__ = 'olympiad_seasons'
    __table_args__ = (
        UniqueConstraint(
            'olympiad_id', 'season_label', name='uq_olympiad_seasons_olympiad_label'
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    olympiad_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    season_label = Column(String, nullable=False)
    #: Версия нужна откату и защите от параллельной правки.
    version = Column('version', Integer, nullable=False, default=1)
    #: Архивный сезон остаётся доступным: профили и правила не удаляются.
    is_archived = Column(Boolean, nullable=False, default=False, index=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    olympiad = relationship('Olympiads', backref='seasons')
    profiles = relationship(
        'SeasonProfile',
        back_populates='season',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )


class SeasonProfile(Base):
    __tablename__ = 'season_profiles'
    __table_args__ = (
        UniqueConstraint(
            'season_id', 'name_norm', name='uq_season_profiles_season_name'
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiad_seasons.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    #: Нормализованное название: уникальность профиля внутри сезона.
    name_norm = Column(String, nullable=False, index=True)
    #: Уровень РСОШ конкретного профиля конкретного сезона: '1', '2', '3' или
    #: NULL, если профиль не входит в перечень.
    rsosh_level = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    version = Column('version', Integer, nullable=False, default=1)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    season = relationship('OlympiadSeason', back_populates='profiles')
