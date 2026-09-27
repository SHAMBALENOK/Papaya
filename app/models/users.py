import uuid
from datetime import datetime, timezone
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, Column, ForeignKey, String, Boolean


class Users(Base):
    """Пользователь Papaya.

    Роли платформы:

    - ``USER`` — обычный посетитель: каталоги, поиск и страницы сущностей
      доступны и без записи о каталоге;
    - ``EDITOR`` — представитель университета: управляет связями своего
      университета с олимпиадами каталога (поле ``university_id``). Создавать
      новые олимпиады представитель не может;
    - ``ADMIN`` — администратор Papaya: каталог олимпиад и университетов,
      импорт документов РСОШ, модерация связей и пользователей.

    ``university_id`` связывает пользователя максимум с одним университетом и
    может быть NULL (у обычного пользователя и у администратора). Для роли
    ``EDITOR`` поле обязательно: именно оно определяет, чьи связи БВИ
    представитель вправе менять (object-level доступ).
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
    university_id = Column(
        UUID(as_uuid=True),
        ForeignKey('universities.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
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