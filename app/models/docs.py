import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Docs(Base):
    """Документ-источник данных Papaya.

    Документ — это не пользовательский продукт, а источник данных: файл или
    ссылка, из которых взята информация об олимпиадах. По полю ``source_doc_id``
    у олимпиады пользователь может увидеть, откуда взялась информация.

    Типы документов (``type``):

    - ``RSOSH_LIST`` — перечень олимпиад РСОШ (основной источник каталога);
    - ``UNIVERSITY_ORDER`` — приказ/положение университета о льготах;
    - ``OTHER`` — любой другой документ-источник.

    ``status`` — состояние обработки документа и одновременно состояние
    импорта РСОШ: ``UPLOADED`` → ``PROCESSING`` → ``PROCESSED`` /
    ``NEEDS_REVIEW`` / ``FAILED`` (либо ``REJECTED``, если администратор
    отклонил результаты импорта).

    ``metadata`` хранит служебный раздел ``rsosh`` — состояние импорта,
    сводку и кандидатов для подтверждения (см. ``app/rsosh/states.py``).
    Отдельная таблица для прогонов импорта не нужна: прогон — это обработка
    конкретного документа.
    """

    __tablename__ = 'docs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False, default='RSOSH_LIST', index=True)
    storage_key = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    checksum = Column(String, nullable=True)
    status = Column(String, nullable=False, default='UPLOADED', index=True)
    processedAt = Column(DateTime(timezone=True), nullable=True)
    # Атрибут ``meta``: имя ``metadata`` зарезервировано Declarative API,
    # а колонка в БД так и называется (``docs.metadata``).
    meta = Column('metadata', JSONB, nullable=True)
    note = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), default=_utcnow, index=True)
    updatedAt = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
