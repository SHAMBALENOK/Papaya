import uuid
from datetime import datetime, timezone
from app.database.base import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import DateTime, Column, String, ForeignKey


class Docs(Base):
    """Документ-источник Papaya.

    ``Docs`` — не просто файловое хранилище: это сущность, представляющая
    документ, на основании которого Papaya получает, валидирует и подтверждает
    данные. Оригинальный документ сохраняется после импорта (см. правила
    «Документ → Источник информации → Papaya data»).

    Документ может быть связан:
      - только с организацией (``organization_id``, ``olympiad_id`` = NULL);
      - только с олимпиадой (``olympiad_id``, ``organization_id`` = NULL);
      - с обоими (например, приказ университета о БВИ конкретной олимпиаде).

    Документ может существовать только по ``source_url`` без локальной копии
    (``storage_key`` = NULL).

    ``status`` описывает состояние обработки и одновременно техническое
    состояние RSOSH-импорта: UPLOADED → PROCESSING → PROCESSED /
    NEEDS_REVIEW / FAILED. Результаты импорта хранятся в ``metadata``.
    """

    __tablename__ = 'docs'

    DOC_TYPES = ('RSOSH_LIST', 'OLYMPIAD_REGULATION', 'UNIVERSITY_DOCUMENT', 'OTHER')
    DOC_STATUSES = ('UPLOADED', 'PROCESSING', 'PROCESSED', 'NEEDS_REVIEW', 'FAILED')

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False, default='OTHER')
    # Безопасное имя файла в хранилище (не доверяем имени пользователя).
    storage_key = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True)
    olympiad_id = Column(UUID(as_uuid=True), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), nullable=True)
    checksum = Column(String, nullable=True)
    status = Column(String, nullable=False, default='UPLOADED')
    metadata_ = Column('metadata', JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )