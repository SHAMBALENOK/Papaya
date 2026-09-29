"""Схемы каталога университетов.

Контракт разделён на Create / Update / Response: серверные поля (id, метки
времени, нормализованное имя) в клиентских схемах отсутствуют, поэтому
клиент не может подменить ``name_norm`` и сломать дедупликацию.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.urls import ExternalUrl


class UniversityBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    name_norm: Optional[str] = None
    short_name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v


class UniversityCreate(BaseModel):
    """Создание университета.

    Не принимает id, ``name_norm`` и метки времени — их задаёт сервер.
    """

    name: str
    short_name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None

    @field_validator('name')
    @classmethod
    def _name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError('name is required')
        return v.strip()


class UniversityUpdate(BaseModel):
    """Частичное обновление университета. Все поля опциональны."""

    name: Optional[str] = None
    short_name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None


class UniversityResponse(UniversityBase):
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
