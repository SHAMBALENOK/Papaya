"""Схемы сезонов и профилей олимпиад (ТЗ §4.2, §4.4)."""

from typing import List, Optional

from pydantic import BaseModel, field_validator

#: Допустимые состояния сезона — продублированы из слоя данных намеренно:
#: схемы не должны зависеть от ``app.database`` (иначе появляется цикл импорта
#: ``database → middlewares → …``). Значения совпадают с
#: ``app.database.seasons.SEASON_STATES``.
SEASON_STATES = ('unknown', 'upcoming', 'active', 'completed')


class SeasonUpsert(BaseModel):
    year: int
    rsoh_level: Optional[str] = None
    state: str = 'unknown'
    dates: Optional[dict] = None
    description: Optional[str] = None
    source_url: Optional[str] = None

    @field_validator('state')
    @classmethod
    def _check_state(cls, v):
        if v not in SEASON_STATES:
            raise ValueError('state must be one of ' + ', '.join(SEASON_STATES))
        return v


class SeasonItem(BaseModel):
    id: str | None = None
    olympiad_id: str | None = None
    year: int | None = None
    rsoh_level: str | None = None
    state: str | None = None
    dates: dict | None = None
    description: str | None = None
    source_url: str | None = None
    source_doc_id: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class SeasonWithProfiles(SeasonItem):
    profiles: List[dict] = []


class SeasonsResponse(BaseModel):
    seasons: List[SeasonWithProfiles]


class ProfileCreate(BaseModel):
    name: str
    subject: Optional[str] = None
    description: Optional[str] = None


class ProfileItem(BaseModel):
    id: str | None = None
    season_id: str | None = None
    name: str | None = None
    name_norm: str | None = None
    subject: str | None = None
    description: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class ProfilesResponse(BaseModel):
    profiles: List[ProfileItem]
