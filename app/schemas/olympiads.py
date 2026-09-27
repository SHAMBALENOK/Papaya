"""Схемы каталога олимпиад.

Олимпиада — единая сущность каталога, независимая от года. Схема записи не
принимает ``status``: актуальность определяется импортом РСОШ и архивированием
(см. ``app/rsosh/persist.py``) либо администратором через отдельный маршрут.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

OLYMPIAD_STATUSES = ('PUBLISHED', 'ARCHIVED')


class OlympiadBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    name_norm: Optional[str] = None
    description: Optional[str] = None
    official_url: Optional[str] = None
    image: Optional[str] = None
    source_url: Optional[str] = None
    source_doc_id: Optional[UUID] = None
    status: str = 'PUBLISHED'

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v not in OLYMPIAD_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(OLYMPIAD_STATUSES))
        return v


class OlympiadCreate(BaseModel):
    """Создание олимпиады вручную (администратором).

    Единственный автоматический способ добавить олимпиаду — импорт документов
    РСОШ; ручное создание остаётся резервным путём для редких случаев.
    """

    name: str
    description: Optional[str] = None
    official_url: Optional[str] = None
    image: Optional[str] = None
    source_url: Optional[str] = None

    @field_validator('name')
    @classmethod
    def _name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError('name is required')
        return v.strip()


class OlympiadUpdate(BaseModel):
    """Частичное обновление олимпиады. Все поля опциональны."""

    name: Optional[str] = None
    description: Optional[str] = None
    official_url: Optional[str] = None
    image: Optional[str] = None
    source_url: Optional[str] = None
    status: Optional[str] = None

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v is not None and v not in OLYMPIAD_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(OLYMPIAD_STATUSES))
        return v


class OlympiadResponse(OlympiadBase):
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
