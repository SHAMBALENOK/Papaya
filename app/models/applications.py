import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RepresentativeApplication(Base):
    """Заявка на роль представителя вуза (ТЗ §3.4).

    Пользователь подаёт заявку с указанием вуза и обоснованием, администратор
    одобряет или отклоняет. Обязательной загрузки подтверждающих документов на
    этапе MVP не требуется.

    Одобрение заявки выдаёт роль ``EDITOR`` с привязкой к университету — через
    тот же защищённый путь ``database.users.apply_role_guarded``, что и ручное
    назначение: второго способа стать представителем быть не должно.
    """

    __tablename__ = 'representative_applications'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    motivation = Column(Text, nullable=True)
    #: PENDING → APPROVED / REJECTED. Отклонённая заявка сохраняется с причиной.
    status = Column(String, nullable=False, default='PENDING', index=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    user = relationship('Users', foreign_keys=[user_id])
    university = relationship('Universities')
