import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')


class BenefitRule(Base):
    __tablename__ = 'benefit_rules'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    olympiad_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    season_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiad_seasons.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey('season_profiles.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    benefit_type = Column(String, nullable=False, default='BVI', index=True)
    required_result = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    additional_requirements = Column(Text, nullable=True)
    doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
    )
    source_url = Column(String, nullable=True)
    verification_status = Column(String, nullable=False, default='unverified', index=True)
    rejection_reason = Column(Text, nullable=True)
    is_published = Column('is_published', Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    university = relationship('Universities', backref='benefit_rules')
    olympiad = relationship('Olympiads', backref='benefit_rules')
    season = relationship('OlympiadSeason', backref='benefit_rules')
    profile = relationship('SeasonProfile', backref='benefit_rules')
    doc = relationship('Docs', backref='benefit_rules')
    programs = relationship(
        'UniversityProgram',
        secondary='benefit_rule_programs',
        backref='benefit_rules',
    )


class BenefitRuleProgram(Base):
    __tablename__ = 'benefit_rule_programs'
    __table_args__ = (
        UniqueConstraint('rule_id', 'program_id', name='uq_benefit_rule_programs_pair'),
    )

    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('benefit_rules.id', ondelete='CASCADE'),
        primary_key=True,
    )
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey('university_programs.id', ondelete='CASCADE'),
        primary_key=True,
    )


class BenefitRuleVersion(Base):
    __tablename__ = 'benefit_rule_versions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('benefit_rules.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    changed_fields = Column(JSONB, nullable=True)
    change_reason = Column(Text, nullable=True)
    verification_status = Column(String, nullable=True)
    doc_id = Column(UUID(as_uuid=True), ForeignKey('docs.id', ondelete='SET NULL'), nullable=True)
    source_url = Column(String, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    changed_at = Column(DateTime(timezone=True), default=_utcnow, index=True)


class BenefitStatusHistory(Base):
    __tablename__ = 'benefit_status_history'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('benefit_rules.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    changed_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
    reason = Column(Text, nullable=True)