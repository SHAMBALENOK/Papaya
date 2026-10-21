import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UniversityBvi(Base):
    """Связь «университет даёт БВИ за олимпиаду» — ядро продукта Papaya.

    Связь ссылается на СУЩЕСТВУЮЩУЮ олимпиаду каталога: университет выбирает
    олимпиаду из общего каталога, а не создаёт свою копию. Уникальное
    ограничение по паре (университет, олимпиада) делает дубли невозможными
    даже на уровне БД.

    ``status`` — состояние заявки (модерация):

    - ``PENDING`` — представитель университета заявил, что вуз даёт БВИ;
      такая связь ещё не видна в публичных списках;
    - ``CONFIRMED`` — администратор подтвердил связь, она видна всем.

    Публично видны только подтверждённые связи: заявка — это рабочий процесс
    модерации, а не публичный факт.
    """

    __tablename__ = 'university_olympiads'
    __table_args__ = (
        UniqueConstraint(
            'university_id',
            'olympiad_id',
            name='uq_university_olympiads_pair',
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
    # Связь хранит двух участников решения: кто заявил (``createdBy``) и кто
    # подтвердил (``confirmedBy``). Инвариант: подтверждение есть только у
    # ``CONFIRMED`` — у ``PENDING`` ``confirmedBy`` всегда NULL, иначе по записи
    # нельзя понять, кто сейчас отвечает за связь.
    status = Column(String, nullable=False, default='PENDING', index=True)
    createdBy = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    confirmedBy = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    # Происхождение связи: документ-источник (приказ вуза, из которого связь
    # распознана) и распознанные характеристики строки (направление, профиль,
    # предмет, уровень, диплом, сезон). У заявки представителя оба поля пусты:
    # там источник — сам представитель, а не документ. Модель «сезон/профиль» в
    # Papaya отсутствует, поэтому распознанные поля хранятся как есть и не
    # создают отдельных сущностей каталога.
    source_doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
    )
    source_meta = Column(JSONB, nullable=True)

    # --- Правило льготы (требования ТЗ §4.3) -------------------------------
    # Вид льготы: 'BVI' (без вступительных испытаний), 'EGE_100' (100 баллов
    # ЕГЭ), 'DVI_100' (100 баллов за ДВИ), 'OTHER' (иные преимущества).
    # Существующие связи по умолчанию — БВИ.
    benefit_type = Column(String, nullable=False, default='BVI', index=True)
    # Требуемый результат: 'winner' (победитель), 'prize' (призёр) или иной.
    result_requirement = Column(String, nullable=True)
    # Предмет/дисциплина, к которой относится льгота.
    subject = Column(String, nullable=True)
    # Образовательные программы вуза, на которые распространяется льгота
    # (список строк). Хранится рядом со связью: отдельных сущностей
    # «программа льготы» в MVP нет.
    programs = Column(JSONB, nullable=True)
    # Дополнительные требования вуза текстом.
    extra_requirements = Column(Text, nullable=True)
    # Ссылка на официальный источник правила.
    source_url = Column(String, nullable=True)
    # Срок действия правила, если известен.
    valid_until = Column(Date, nullable=True)

    # --- Проверка (требования ТЗ §7.1) -------------------------------------
    # Независимая характеристика: проверка администрацией Papaya. Это НЕ статус
    # заявки (``status``): заявка может быть подтверждена, но сведения ещё не
    # проверены, и наоборот.
    # ``unverified`` — не проверено; ``verified`` — проверено; ``rejected`` —
    # отклонено как ошибочное.
    verification_status = Column(
        String, nullable=False, default='unverified', index=True
    )
    verified_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    # Подтверждение со стороны вуза — отдельная характеристика: оно не
    # тождественно проверке администрацией Papaya.
    university_confirmed = Column(
        Boolean, nullable=False, default=False
    )
    university_confirmed_at = Column(DateTime(timezone=True), nullable=True)

    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    university = relationship('Universities', back_populates='bvi_links')
    olympiad = relationship('Olympiads', back_populates='bvi_links')
    # История версий правила: удаляется вместе со связью.
    versions = relationship(
        'BenefitRuleVersion',
        back_populates='link',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='BenefitRuleVersion.version',
    )
