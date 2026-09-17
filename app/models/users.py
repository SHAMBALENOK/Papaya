import uuid
from datetime import datetime, timezone
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, Column, String, Boolean


class Users(Base):
    """Пользователь Papaya.

    Роль может быть одной из: USER (обычный школьник), EDITOR (создаёт и
    правит события) или ADMIN (администратор платформы).
    """

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
    # Индекс помогает сортировке списков пользователей по дате создания.
    # Timezone-aware, как и в events, чтобы обе таблицы имели общий контракт
    # времени (миграция 0003 выровняла legacy-колонки).
    createdAt = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updatedAt = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )