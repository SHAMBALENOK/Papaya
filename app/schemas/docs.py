from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID


class DocBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    type: str = 'OTHER'
    mime_type: Optional[str] = None
    source_url: Optional[str] = None
    organization_id: Optional[UUID] = None
    olympiad_id: Optional[UUID] = None
    status: str = 'UPLOADED'

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        allowed = ('RSOSH_LIST', 'OLYMPIAD_REGULATION', 'UNIVERSITY_DOCUMENT', 'OTHER')
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        allowed = ('UPLOADED', 'PROCESSING', 'PROCESSED', 'NEEDS_REVIEW', 'FAILED')
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class DocCreate(BaseModel):
    """Создание документа.

    Контракт: id, status, checksum и временные метки задаёт сервер.
    ``name``, при необходимости, нормализуется сервером (безопасное имя
    исходного файла передаётся отдельно при загрузке).
    """
    name: str
    type: str = 'OTHER'
    mime_type: Optional[str] = None
    source_url: Optional[str] = None
    organization_id: Optional[UUID] = None
    olympiad_id: Optional[UUID] = None
    metadata: Optional[dict] = None

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        allowed = ('RSOSH_LIST', 'OLYMPIAD_REGULATION', 'UNIVERSITY_DOCUMENT', 'OTHER')
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v


class DocUpdate(BaseModel):
    """Частичное обновление документа. status — отдельный жизненный цикл."""
    name: Optional[str] = None
    type: Optional[str] = None
    mime_type: Optional[str] = None
    source_url: Optional[str] = None
    organization_id: Optional[UUID] = None
    olympiad_id: Optional[UUID] = None
    metadata: Optional[dict] = None

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        if v is not None:
            allowed = ('RSOSH_LIST', 'OLYMPIAD_REGULATION', 'UNIVERSITY_DOCUMENT', 'OTHER')
            if v not in allowed:
                raise ValueError(f"type must be one of {allowed}")
        return v


class DocResponse(DocBase):
    storage_key: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    checksum: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)