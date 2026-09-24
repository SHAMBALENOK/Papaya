import re

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID

from app.core.schedule import STAGE_TYPES


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


class OlympiadStage(BaseModel):
    """Этап олимпиады.

    Контракт: ``status`` этапа в API всегда вычисляется сервером
    (app/core/schedule.py) и в запросе/БД не передаётся. Даты принимаются
    только в формате ISO 8601 с таймзоной (naive значения отклоняются 422 —
    это исключает неоднозначность «в каком поясе начало этапа»).
    """
    id: str
    name: str
    type: str
    start_at: str
    end_at: Optional[str] = None
    timezone: Optional[str] = None

    @field_validator('id')
    @classmethod
    def _check_id(cls, v):
        v = (v or '').strip()
        if not v:
            raise ValueError('stage id is required')
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,63}', v):
            raise ValueError('stage id may contain only letters, digits, "_", "-"')
        return v

    @field_validator('name')
    @classmethod
    def _check_name(cls, v):
        v = (v or '').strip()
        if not v:
            raise ValueError('stage name is required')
        return v

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        v = (v or '').strip().upper()
        if v not in STAGE_TYPES:
            raise ValueError(f"stage type must be one of {STAGE_TYPES}")
        return v

    @field_validator('start_at', 'end_at')
    @classmethod
    def _check_datetime(cls, v):
        if v is None or v == '':
            return None
        try:
            dt = datetime.fromisoformat(str(v))
        except (TypeError, ValueError):
            raise ValueError(
                'must be an ISO 8601 datetime, e.g. "2026-09-01T00:00:00+03:00"'
            )
        if dt.tzinfo is None:
            raise ValueError('must include a timezone offset (e.g. +03:00 or Z)')
        return dt.isoformat()

    @model_validator(mode='after')
    def _check_range(self):
        start = self.start_at
        end = self.end_at
        if end is not None and datetime.fromisoformat(start) > datetime.fromisoformat(end):
            raise ValueError('start_at must not be later than end_at')
        return self


class OlympiadSchedule(BaseModel):
    """Временная структура олимпиады: сезон + упорядоченные этапы.

    ``stages`` должен быть упорядочен по времени старта — это влияет на
    выбор «текущего» этапа при пересечении дат (при прочих равных побеждает
    этап раньше в массиве).
    """
    season: Optional[str] = None
    stages: List[OlympiadStage] = []

    @field_validator('season')
    @classmethod
    def _check_season(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        if not v:
            return None
        if len(v) > 32:
            raise ValueError('season is too long (max 32 chars)')
        return v

    @model_validator(mode='after')
    def _check_duplicate_ids(self):
        seen = set()
        for stage in self.stages:
            if stage.id in seen:
                raise ValueError(f'duplicate stage id: {stage.id!r}')
            seen.add(stage.id)
        return self


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
    schedule: Optional[OlympiadSchedule] = None

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
    schedule: Optional[OlympiadSchedule] = None

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
    # Расписание (Фаза 2): источник данных plus вычисляемые поля.
    # ``schedule.stages[].status``, ``current_status``, ``current_stage`` и
    # ``next_deadline`` заполняются сервером динамически и в БД не хранятся;
    # для старых олимпиад без расписания всё равно NULL.
    schedule: Optional[dict] = None
    current_status: Optional[str] = None
    current_stage: Optional[dict] = None
    next_deadline: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)