import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OlympiadSeason(Base):
    __tablename__ = 'olympiad_seasons'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    olympiad_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    season_label = Column(String, nullable=False)
    rsosh_level = Column(String, nullable=True)
    registration_start = Column(DateTime(timezone=True), nullable=True)
    registration_end = Column(DateTime(timezone=True), nullable=True)
    event_start = Column(DateTime(timezone=True), nullable=True)
    event_end = Column(DateTime(timezone=True), nullable=True)
    extra_params = Column(JSONB, nullable=True)
    availability = Column(String, nullable=False, default='unknown')
    version = Column('version', Integer, nullable=False, default=1)
    source_doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
    )
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiad_seasons.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    discipline = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    profile_name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    extra_params = Column(JSONB, nullable=True)
    version = Column('version', Integer, nullable=False, default=1)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    season = relationship('OlympiadSeason', back_populates='profiles')