from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


def _validate_str_list(value):
    """JSONB-массивы доменов хранят строки (в т.ч. UUID-строки)."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('expected a list')
    for item in value:
        if isinstance(item, UUID):
            item = str(item)
        if not isinstance(item, str):
            raise ValueError('list items must be strings')
    return [str(v) for v in value]


class OlympiadBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    organizer_ids: List[str] = []
    description: Optional[str] = None
    subjects: List[str] = []
    levels: List[str] = []
    years: List[str] = []
    profiles: Optional[List[dict]] = None
    bvi_organizations: List[str] = []
    registration_url: Optional[str] = None
    official_url: Optional[str] = None
    status: str = 'PUBLISHED'

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

    @field_validator('organizer_ids', 'subjects', 'levels', 'years',
                     'bvi_organizations', mode='before')
    @classmethod
    def _norm_lists(cls, v):
        return _validate_str_list(v)

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        allowed = ('DRAFT', 'PUBLISHED', 'ARCHIVED')
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class OlympiadCreate(BaseModel):
    """Создание олимпиады.

    Контракт: id, status и временные метки задаёт сервер (status по
    умолчанию PUBLISHED, но переопределяется только серверной логикой).
    """
    name: str
    organizer_ids: List[str] = []
    description: Optional[str] = None
    subjects: List[str] = []
    levels: List[str] = []
    years: List[str] = []
    profiles: Optional[List[dict]] = None
    bvi_organizations: List[str] = []
    registration_url: Optional[str] = None
    official_url: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator('organizer_ids', 'subjects', 'levels', 'years',
                     'bvi_organizations', mode='before')
    @classmethod
    def _norm_lists(cls, v):
        return _validate_str_list(v)


class OlympiadUpdate(BaseModel):
    """Частичное обновление олимпиады. Все поля опциональны."""
    name: Optional[str] = None
    organizer_ids: Optional[List[str]] = None
    description: Optional[str] = None
    subjects: Optional[List[str]] = None
    levels: Optional[List[str]] = None
    years: Optional[List[str]] = None
    profiles: Optional[List[dict]] = None
    bvi_organizations: Optional[List[str]] = None
    registration_url: Optional[str] = None
    official_url: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator('organizer_ids', 'subjects', 'levels', 'years',
                     'bvi_organizations', mode='before')
    @classmethod
    def _norm_lists(cls, v):
        return _validate_str_list(v)

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v is not None:
            allowed = ('DRAFT', 'PUBLISHED', 'ARCHIVED')
            if v not in allowed:
                raise ValueError(f"status must be one of {allowed}")
        return v


class OlympiadResponse(OlympiadBase):
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)