import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
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
    createdAt = Column(DateTime(timezone=True), default=_utcnow)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    university = relationship('Universities', back_populates='bvi_links')
    olympiad = relationship('Olympiads', back_populates='bvi_links')
