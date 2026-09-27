"""Схемы документов-источников.

Документ — источник данных, а не пользовательский объект: его статус
(``UPLOADED``/``PROCESSING``/``PROCESSED``/``NEEDS_REVIEW``/``FAILED``/
``REJECTED``) отражает состояние обработки, в том числе прогон импорта РСОШ.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

DOC_TYPES = ('RSOSH_LIST', 'UNIVERSITY_ORDER', 'OTHER')
DOC_STATUSES = (
    'UPLOADED',
    'PROCESSING',
    'PROCESSED',
    'NEEDS_REVIEW',
    'FAILED',
    'REJECTED',
)


class DocBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    type: str = 'RSOSH_LIST'
    mime_type: Optional[str] = None
    source_url: Optional[str] = None
    note: Optional[str] = None
    status: str = 'UPLOADED'

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        if v not in DOC_TYPES:
            raise ValueError('type must be one of ' + ', '.join(DOC_TYPES))
        return v

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v not in DOC_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(DOC_STATUSES))
        return v


class DocCreate(BaseModel):
    """Создание записи о документе (без файла — только ссылка)."""

    name: str
    type: str = 'RSOSH_LIST'
    source_url: Optional[str] = None
    note: Optional[str] = None

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        if v not in DOC_TYPES:
            raise ValueError('type must be one of ' + ', '.join(DOC_TYPES))
        return v


class DocUpdate(BaseModel):
    """Частичное обновление документа (кроме жизненного цикла обработки)."""

    name: Optional[str] = None
    type: Optional[str] = None
    note: Optional[str] = None

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        if v is not None and v not in DOC_TYPES:
            raise ValueError('type must be one of ' + ', '.join(DOC_TYPES))
        return v


class DocResponse(DocBase):
    storage_key: Optional[str] = None
    checksum: Optional[str] = None
    processedAt: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
