import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Публикационные состояния правила льготы.
RULE_STATUS_DRAFT = 'draft'
RULE_STATUS_PUBLISHED = 'published'
RULE_STATUS_ARCHIVED = 'archived'
RULE_STATUSES = (RULE_STATUS_DRAFT, RULE_STATUS_PUBLISHED, RULE_STATUS_ARCHIVED)

#: Статусы проверки Papaya — независимы от публикационного состояния.
VERIFICATION_UNVERIFIED = 'unverified'
VERIFICATION_VERIFIED = 'verified'
VERIFICATION_REJECTED = 'rejected'
VERIFICATION_STATUSES = (
    VERIFICATION_UNVERIFIED,
    VERIFICATION_VERIFIED,
    VERIFICATION_REJECTED,
)

#: Виды льгот (ТЗ §4.3).
BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')


class BenefitRule(Base):
    """Правило льготы — ядро продукта Papaya (ТЗ §4.3, §9).

    Правило связывает **существующие** сущности каталога: университет,
    олимпиаду и (необязательно) конкретный сезон и профиль олимпиады, а также
    набор образовательных программ вуза (``benefit_rule_programs``). Пара
    «университет — олимпиада» может иметь несколько правил: разные сезоны,
    профили, виды льгот и программы дают разные условия.

    Две независимые характеристики:

    - ``status`` — публикационное состояние: ``draft`` (черновик, виден только
      представителю своего вуза и администратору), ``published`` (виден в
      каталоге), ``archived`` (история, не показывается как действующее);
    - ``verification_status`` — проверка администрацией Papaya:
      ``unverified`` / ``verified`` / ``rejected``. Опубликованное, но не
      проверенное правило показывается с пометкой «Не проверено Papaya».
      Отклонённое правило не выдаётся за действующее.

    ``university_confirmed`` — подтверждение со стороны вуза; это **не**
    проверка Papaya и на ``verification_status`` не влияет.

    ``version`` — номер последней записанной версии (оптимистическая
    блокировка: клиент передаёт ``expected_version``, и при расхождении
    получает 409 вместо молчаливой перезаписи чужих правок).

    ``dedup_key`` — детерминированный ключ содержимого (сезон, профиль, вид
    льготы, результат, предмет, набор программ); уникальный частичный индекс по
    (университет, олимпиада, ключ) запрещает два одинаковых действующих
    правила даже при гонке двух запросов, но не мешает архиву хранить историю.
    """

    __tablename__ = 'benefit_rules'
    __table_args__ = (
        # Сезон принадлежит той же олимпиаде, что и правило; профиль — тому же
        # сезону. Составные внешние ключи держат это на уровне БД, а не только
        # в коде.
        ForeignKeyConstraint(
            ['season_id', 'olympiad_id'],
            ['olympiad_seasons.id', 'olympiad_seasons.olympiad_id'],
            name='fk_benefit_rules_season_olympiad',
        ),
        ForeignKeyConstraint(
            ['profile_id', 'season_id'],
            ['olympiad_profiles.id', 'olympiad_profiles.season_id'],
            name='fk_benefit_rules_profile_season',
        ),
        CheckConstraint(
            'profile_id IS NULL OR season_id IS NOT NULL',
            name='ck_benefit_rules_profile_requires_season',
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name='ck_benefit_rules_status',
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')",
            name='ck_benefit_rules_verification_status',
        ),
        Index(
            'ux_benefit_rules_dedup',
            'university_id',
            'olympiad_id',
            'dedup_key',
            unique=True,
            postgresql_where="status <> 'archived'",
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
    season_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    profile_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    status = Column(String, nullable=False, default=RULE_STATUS_DRAFT, index=True)
    createdBy = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    published_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    published_at = Column(DateTime(timezone=True), nullable=True)

    # Официальный документ вуза (приказ/правила приёма), подтверждающий
    # правило, и происхождение записи из импорта (распознанные поля строки).
    source_doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
    )
    source_meta = Column(JSONB, nullable=True)

    benefit_type = Column(String, nullable=False, default='BVI', index=True)
    result_requirement = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    extra_requirements = Column(Text, nullable=True)
    source_url = Column(String, nullable=True)
    valid_until = Column(Date, nullable=True)

    verification_status = Column(
        String, nullable=False, default=VERIFICATION_UNVERIFIED, index=True
    )
    verified_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    #: Причина отклонения / комментарий проверяющего.
    verification_note = Column(Text, nullable=True)

    university_confirmed = Column(Boolean, nullable=False, default=False)
    university_confirmed_at = Column(DateTime(timezone=True), nullable=True)

    version = Column(Integer, nullable=False, default=0)
    dedup_key = Column(String, nullable=False, default='')

    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    university = relationship('Universities', back_populates='benefit_rules')
    olympiad = relationship('Olympiads', back_populates='benefit_rules')
    versions = relationship(
        'BenefitRuleVersion',
        back_populates='rule',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='BenefitRuleVersion.version',
    )
    program_links = relationship(
        'BenefitRuleProgram',
        back_populates='rule',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )


class BenefitRuleProgram(Base):
    """Связь «правило льготы — образовательная программа вуза» (M2M).

    ``university_id`` дублируется намеренно: составной внешний ключ
    ``(program_id, university_id) → university_programs(id, university_id)``
    гарантирует, что к правилу нельзя привязать программу чужого вуза.
    Удаление программы, на которую ссылаются правила, блокируется (NO ACTION):
    сначала нужно убрать её из правил.
    """

    __tablename__ = 'benefit_rule_programs'
    __table_args__ = (
        ForeignKeyConstraint(
            ['program_id', 'university_id'],
            ['university_programs.id', 'university_programs.university_id'],
            name='fk_benefit_rule_programs_program_university',
        ),
    )

    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('benefit_rules.id', ondelete='CASCADE'),
        primary_key=True,
    )
    program_id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    university_id = Column(UUID(as_uuid=True), nullable=False)

    rule = relationship('BenefitRule', back_populates='program_links')
    program = relationship(
        'UniversityProgram',
        primaryjoin='BenefitRuleProgram.program_id == UniversityProgram.id',
        foreign_keys=[program_id],
        viewonly=True,
    )
