"""Правила предоставления льгот и связанные структуры.

Правило — утверждение «университет U за профиль P сезона S олимпиады O даёт
льготу T тем, кто показал результат R, на основании документа D».

Отдельной сущности «БВИ» нет: БВИ — значение ``benefit_type``. Требование по
ЕГЭ — самостоятельная необязательная запись: профиль олимпиады отвечает за то,
за что получен диплом, а предмет ЕГЭ — за то, какой экзамен нужно подтвердить.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Тип льготы: БВИ, 100 баллов ЕГЭ, 100 баллов ДВИ, другая льгота.
BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')

#: Требуемый результат олимпиады. Свободного текста здесь нет.
REQUIRED_RESULT_TYPES = ('WINNER', 'PRIZE', 'WINNER_OR_PRIZE')

VERIFICATION_STATUSES = ('unverified', 'verified', 'rejected')


class BenefitRule(Base):
    __tablename__ = 'benefit_rules'
    __table_args__ = (
        CheckConstraint(
            "benefit_type IN ('BVI', 'EGE_100', 'DVI_100', 'OTHER')",
            name='ck_benefit_rules_type',
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')",
            name='ck_benefit_rules_status',
        ),
        CheckConstraint(
            "required_result_type IS NULL OR "
            "required_result_type IN ('WINNER', 'PRIZE', 'WINNER_OR_PRIZE')",
            name='ck_benefit_rules_result_type',
        ),
    )

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
    #: Сезон и профиль обязательны по смыслу. NULL остаётся только у
    #: исторических записей, перенесённых из старой модели БВИ: их нельзя
    #: удалить, но и выдумывать им сезон нельзя — они ждут ручной проверки.
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
    required_result_type = Column(String, nullable=True)
    #: Документ университета, на основании которого действует льгота.
    doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    #: Правило перенесено из старой модели и требует ручного заполнения
    #: сезона/профиля или проверки основания.
    needs_review = Column(Boolean, nullable=False, default=False, index=True)
    verification_status = Column(
        String, nullable=False, default='unverified', index=True
    )
    rejection_reason = Column(Text, nullable=True)
    is_published = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    updated_by = Column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    university = relationship('Universities', backref='benefit_rules')
    olympiad = relationship('Olympiads', backref='benefit_rules')
    season = relationship('OlympiadSeason', backref='benefit_rules')
    profile = relationship('SeasonProfile', backref='benefit_rules')
    doc = relationship('Docs', backref='benefit_rules')
    ege_requirement = relationship(
        'BenefitEgeRequirement',
        back_populates='rule',
        uselist=False,
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    migration_issues = relationship(
        'BenefitRuleMigrationIssue',
        back_populates='rule',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )


class BenefitEgeRequirement(Base):
    """Необязательное подтверждение результата ЕГЭ для льготы."""

    __tablename__ = 'benefit_ege_requirements'
    __table_args__ = (
        UniqueConstraint('rule_id', name='uq_benefit_ege_requirements_rule'),
        CheckConstraint(
            'min_score IS NULL OR (min_score >= 0 AND min_score <= 100)',
            name='ck_benefit_ege_min_score',
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('benefit_rules.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    subject = Column(String, nullable=False)
    min_score = Column(Integer, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    rule = relationship('BenefitRule', back_populates='ege_requirement')


class BenefitRuleVersion(Base):
    __tablename__ = 'benefit_rule_versions'
    __table_args__ = (
        UniqueConstraint(
            'rule_id', 'version_number',
            name='uq_benefit_rule_versions_rule_version',
        ),
    )

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
    doc_id = Column(
        UUID(as_uuid=True), ForeignKey('docs.id', ondelete='SET NULL'), nullable=True
    )
    changed_by = Column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
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
    changed_by = Column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    changed_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
    reason = Column(Text, nullable=True)


class BenefitRuleMigrationIssue(Base):
    """Непереведённое однозначно поле: очередь ручной проверки.

    Записи не удаляют исходные данные: ``raw_value`` хранит то, что было в
    старом поле, чтобы администратор мог решить вручную.
    """

    __tablename__ = 'benefit_rule_migration_issues'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('benefit_rules.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    entity_type = Column(String, nullable=False, default='benefit_rule', index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    field = Column(String, nullable=True)
    raw_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False, index=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)

    rule = relationship('BenefitRule', back_populates='migration_issues')
