"""Типы данных импорта РСОШ.

Импортёр работает не с таблицами как таковыми, а с «записями об олимпиадах»
и понятным отчётом о том, что удалось и что не удалось распознать. Эти
структуры — общий контракт между этапами pipeline и HTTP-слоем (preview).
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# Действие, которое будет выполнено при подтверждении импорта.
Action = Literal['create', 'merge', 'skip']
# Уверенность в сопоставлении с существующим каталогом.
Confidence = Literal['ok', 'review']
# Способ получения данных страницы.
Method = Literal['xlsx', 'text', 'ocr']


@dataclass
class PageReport:
    """Что произошло на одной странице документа."""

    page: int
    method: Method
    orientation: int = 0
    rotation_applied: int = 0
    tables: int = 0
    rows: int = 0
    chars: int = 0
    confidence: float = 1.0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OlympiadRecord:
    """Одна олимпиада, извлечённая из документа.

    ``description`` заполняется, если в документе есть колонка с описанием
    (в перечнях РСОШ её обычно нет — тогда остаётся None, и это нормально).
    Дополнительные характеристики (предмет, уровень, классы) намеренно не
    извлекаются: концепция Papaya их не требует.
    """

    name: str
    name_norm: str
    description: str | None = None
    page: int | None = None
    row: int | None = None
    raw: str = ''
    confidence: float = 1.0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    """Кандидат каталога, готовый к записи (после дедупликации)."""

    name: str
    name_norm: str
    description: str | None = None
    action: Action = 'create'
    matched_olympiad_id: str | None = None
    match_score: float = 0.0
    confidence: Confidence = 'ok'
    page: int | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Candidate':
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ExtractionResult:
    """Результат чтения документа: записи, отчёт и сводка."""

    records: list[OlympiadRecord] = field(default_factory=list)
    pages: list[PageReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {'total': len(self.records)}

    @property
    def mean_confidence(self) -> float:
        if not self.records:
            return 0.0
        return round(
            sum(record.confidence for record in self.records) / len(self.records),
            3,
        )


class RsoshError(Exception):
    """Ошибка импорта РСОШ, понятная администратору."""


class RsoshConflictError(RsoshError):
    """Действие конфликтует с текущим состоянием каталога.

    Отдельный тип нужен, чтобы HTTP-слой отличал «плохой запрос» (400) от
    «состояние не позволяет» (409). Например, подтверждение устаревшего
    перечня — запрос корректный, но применять его нельзя.
    """
