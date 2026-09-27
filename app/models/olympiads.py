import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Olympiads(Base):
    """Олимпиада — единая каноническая сущность каталога Papaya.

    Одна олимпиада существует в каталоге независимо от года проведения:
    отдельных записей «олимпиада 2026» и «олимпиада 2027» Papaya не создаёт.
    Год — это часть описания, а не отдельная сущность.

    Статус актуальности:

    - ``PUBLISHED`` — олимпиада входит в актуальный перечень РСОШ;
    - ``ARCHIVED`` — олимпиады больше нет в актуальном перечне РСОШ, запись
      сохранена исторически и помечена в интерфейсе (архив не удаляет данные).

    Почему архивировано — ``archive_reason``:

    - ``RSOSH_ABSENT`` — импорт РСОШ не нашёл олимпиаду в актуальном перечне.
      Вернуть её в актуальные вручную нельзя: это сделает только следующий
      импорт, где олимпиада снова встретится;
    - ``MANUAL`` — администратор исключил олимпиаду из актуального каталога
      руками (например, из-за ошибки в данных). Такую запись можно вернуть.

    Причина архивирования хранится, потому что статус один, а решение о нём
    принимают два разных механизма; без причины ручное «вернуть» выдавало бы
    олимпиаду за актуальную по перечню РСОШ, чего нет.

    ``source_doc_id`` — документ-источник, из которого взяты данные
    (загруженный документ РСОШ). По нему пользователь видит, откуда взялась
    информация об олимпиаде, и по нему же определяется, какие олимпиады ещё
    присутствуют в актуальном перечне.

    Изображений два: ``preview_image`` — для карточек каталога, ``image`` — для
    страницы олимпиады. Оба необязательны, интерфейс использует fallback.
    """

    __tablename__ = 'olympiads'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    # Нормализованное имя: уникальность каталога (одна олимпиада — одна
    # запись независимо от написания) и ключ сопоставления при импорте.
    name_norm = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    official_url = Column(String, nullable=True)
    # Маленькая картинка для карточек каталога.
    preview_image = Column(String, nullable=True)
    # Большая картинка для страницы олимпиады.
    image = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    source_doc_id = Column(
        UUID(as_uuid=True),
        ForeignKey('docs.id', ondelete='SET NULL'),
        nullable=True,
    )
    status = Column(String, nullable=False, default='PUBLISHED', index=True)
    # Причина архивирования: 'RSOSH_ABSENT' (нет в актуальном перечне РСОШ) или
    # 'MANUAL' (исключена администратором). NULL, когда олимпиада актуальна.
    archive_reason = Column(String, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    bvi_links = relationship(
        'UniversityBvi',
        back_populates='olympiad',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
