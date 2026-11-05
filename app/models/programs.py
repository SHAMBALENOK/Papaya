import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UniversityProgram(Base):
    __tablename__ = 'university_programs'
    __table_args__ = (
        UniqueConstraint('university_id', 'name_norm', name='uq_university_programs_pair'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    name_norm = Column(String, nullable=False, index=True)
    code = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    version = Column('version', Integer, nullable=False, default=1)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    university = relationship('Universities', backref='programs')