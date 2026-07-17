import uuid
from datetime import datetime
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, Column, String, Boolean


class Users(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    surname = Column(String, nullable=False)
    gender = Column(String, nullable=True)
    bday = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    status = Column(String, nullable=True)
    role = Column(String, default='USER')
    isActive = Column(Boolean, default=True)
    createdAt = Column(DateTime, default=datetime.now)
    updatedAt = Column(DateTime, default=datetime.now, onupdate=datetime.now)