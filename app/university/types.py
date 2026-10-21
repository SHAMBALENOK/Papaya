"""Типы данных импорта приказа университета.

Импорт приказа вуза отличается от импорта перечня РСОШ по смыслу: перечень
РСОШ создаёт **олимпиады** каталога, а приказ вуза создаёт **связи БВИ**
«этот университет даёт БВИ за эту олимпиаду». Олимпиада при этом берётся из
существующего каталога — приказ не создаёт олимпиад (см. ``persist.py``).

Эти структуры — общий контракт между этапами разбора и HTTP-слоем (preview).
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# Действие, которое будет выполнено при подтверждении импорта.
#: ``link`` — создать/обновить связь БВИ; ``skip`` — строка снята администратором.
Action = Literal['link', 'skip']
# Уверенность в сопоставлении олимпиады со строкой каталога.
Confidence = Literal['ok', 'review']
# Способ получения данных страницы (совпадает с РСОШ: общий extraction).
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
class UniversityRecord:
    """Одна строка приказа: олимпиада, за которую вуз даёт БВИ.

    ``olympiad_name`` — название из приказа; по нему строка сопоставляется с
    существующей олимпиадой каталога. Распознанные характеристики строки
    (направление, профиль, предмет, уровень, диплом) хранятся в ``meta``:
    сущностей «сезон/профиль» в модели Papaya нет, поэтому они не создают
    отдельных записей каталога, а сохраняются как есть рядом со связью.
    """

    olympiad_name: str
    name_norm: str
    meta: dict[str, Any] = field(default_factory=dict)
    page: int | None = None
    row: int | None = None
    raw: str = ''
    confidence: float = 1.0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UniversityRecord':
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class UniversityCandidate:
    """Строка приказа, готовая к записи связи БВИ (после сопоставления).

    ``olympiad_id`` — существующая олимпиада каталога, с которой строка
    сопоставлена. Пусто, если автоматически сопоставить не удалось: тогда
    администратор выбирает олимпиаду в окне проверки, и без его выбора строка
    не применяется (приказ не создаёт олимпиад).
    """

    olympiad_name: str
    name_norm: str
    olympiad_id: str | None = None
    matched_name: str | None = None
    match_score: float = 0.0
    action: Action = 'link'
    confidence: Confidence = 'ok'
    meta: dict[str, Any] = field(default_factory=dict)
    page: int | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UniversityCandidate':
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in known})


class UniversityError(Exception):
    """Ошибка импорта приказа университета, понятная администратору."""


class UniversityConflictError(UniversityError):
    """Действие конфликтует с текущим состоянием документа/каталога.

    Отдельный тип нужен, чтобы HTTP-слой отличал «плохой запрос» (400) от
    «состояние не позволяет» (409).
    """
