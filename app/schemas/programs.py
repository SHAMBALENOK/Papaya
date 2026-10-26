"""Схемы образовательных программ университета (ТЗ §4.1).

Программа — это перечень направлений подготовки вуза. Она используется как
область действия правила льготы («льгота действует на программу X») и как
фильтр в каталоге. Набор программ ведёт вуз, поэтому правка закрыта
представителем и администратором.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class UniversityProgramItem(BaseModel):
    """Одна образовательная программа вуза."""

    id: Optional[UUID] = None
    university_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    #: Сколько правил льгот ссылается на программу: такую программу нельзя
    #: удалить, пока её не убрали из правил.
    rules_count: int = 0


class UniversityProgramCreate(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator('name')
    @classmethod
    def _name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError('name is required')
        return v.strip()


class UniversityProgramsResponse(BaseModel):
    programs: List[UniversityProgramItem]
    total: int = 0


class UniversityProgramsUpdate(BaseModel):
    """Полная замена набора программ.

    Набор задаётся целиком, а не по одному: так правка не требует отдельного
    запроса на добавление и удаление, а интерфейсу не нужен счётчик версий.
    Пустые и повторяющиеся названия отбрасываются на сервере.
    """

    programs: List[str] = []

    @field_validator('programs')
    @classmethod
    def _check_programs(cls, v):
        if v is None:
            return []
        if len(v) > 200:
            raise ValueError('too many programs')
        return v
