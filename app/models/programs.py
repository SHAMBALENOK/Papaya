import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UniversityProgram(Base):
    """Образовательная программа/направление вуза (ТЗ §4.1).

    Программы используются в фильтрах льгот и как область действия правила:
    одно правило может распространяться на несколько программ вуза.
    """

    __tablename__ = 'university_programs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    name_norm = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    university = relationship('Universities', back_populates='programs')
