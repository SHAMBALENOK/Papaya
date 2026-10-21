import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BenefitRuleVersion(Base):
    """История версий правила льготы (ТЗ §8).

    Каждое сохранение опубликованного правила создаёт новую версию со снимком
    состояния. Откат не удаляет промежуточные версии, а создаёт новую версию на
    основе выбранной старой (``is_rollback``).

    ``snapshot`` хранит полный снимок полей правила на момент изменения: вид
    льготы, результат, предмет, программы, доп. требования, источник, срок
    действия и статус проверки. Полный снимок, а не дельта, выбран намеренно:
    восстановление версии не должно зависеть от того, какие поля менялись в
    промежуточных версиях.
    """

    __tablename__ = 'benefit_rule_versions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    link_id = Column(
        UUID(as_uuid=True),
        ForeignKey('university_olympiads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    #: Порядковый номер версии внутри одного правила (1, 2, 3, ...).
    version = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    changed_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    changed_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
    reason = Column(Text, nullable=True)
    #: Статус проверки на момент изменения — отдельно от текущего статуса.
    verification_status = Column(String, nullable=True)
    #: Сведения об источнике и документе на момент изменения.
    source_doc_id = Column(UUID(as_uuid=True), nullable=True)
    source_meta = Column(JSONB, nullable=True)
    #: Создана ли версия откатом (а не обычным сохранением).
    is_rollback = Column(Boolean, nullable=False, default=False)

    link = relationship('UniversityBvi', back_populates='versions')
