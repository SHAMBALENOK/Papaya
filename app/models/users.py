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
      университета с олимпиадами каталога. Создавать новые олимпиады не
      может;
    - ``ADMIN`` — администратор Papaya: каталог олимпиад и университетов,
      импорт документов РСОШ, модерация связей и пользователей.

    Инвариант роли: ``EDITOR`` всегда привязан к конкретному университету
    (``university_id``). Привязка без роли представителя допустима только для
    ``ADMIN`` — его права от неё не зависят, а сохранение нужно, чтобы
    понижение администратора вернуло роль представителя, а не голого
    пользователя. Инвариант проверяется в ``app.database.users.apply_role`` и
    продублирован CHECK-ограничением в БД.
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