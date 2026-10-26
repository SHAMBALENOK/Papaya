import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Чего не хватает в каталоге: олимпиады, сезона, профиля или иное.
CATALOG_REQUEST_KINDS = ('olympiad', 'season', 'profile', 'other')
CATALOG_REQUEST_STATUSES = ('open', 'resolved', 'rejected')


class CatalogRequest(Base):
    """Запрос представителя вуза к администратору о пополнении каталога.

    Представитель не создаёт олимпиады, сезоны и профили сам (каталог ведёт
    администратор по перечню РСОШ), но ему нужен понятный путь, когда нужной
    записи нет: запрос фиксируется в системе, администратор видит его в
    панели, дополняет каталог и закрывает запрос с комментарием.
    """

    __tablename__ = 'catalog_requests'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    kind = Column(String, nullable=False, default='olympiad')
    #: Олимпиада, к которой относится запрос (для сезона/профиля).
    olympiad_id = Column(
        UUID(as_uuid=True),
        ForeignKey('olympiads.id', ondelete='SET NULL'),
        nullable=True,
    )
    text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default='open', index=True)
    admin_note = Column(Text, nullable=True)
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    university = relationship('Universities')
    olympiad = relationship('Olympiads')
