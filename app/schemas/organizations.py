from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class OrganizationBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    short_name: Optional[str] = None
    type: str = 'OTHER'
    description: Optional[str] = None
    website: Optional[str] = None
    logo: Optional[str] = None
    contacts: Optional[dict] = None

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        allowed = ('UNIVERSITY', 'ORGANIZER', 'SCHOOL', 'OTHER')
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v


class OrganizationCreate(BaseModel):
    """Создание организации.

    Контракт: id, createdAt и updatedAt задаёт сервер.
    """
    name: str
    short_name: Optional[str] = None
    type: str = 'OTHER'
    description: Optional[str] = None
    website: Optional[str] = None
    logo: Optional[str] = None
    contacts: Optional[dict] = None
    metadata: Optional[dict] = None

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        allowed = ('UNIVERSITY', 'ORGANIZER', 'SCHOOL', 'OTHER')
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v


class OrganizationUpdate(BaseModel):
    """Частичное обновление организации. Все поля опциональны."""
    name: Optional[str] = None
    short_name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    logo: Optional[str] = None
    contacts: Optional[dict] = None
    metadata: Optional[dict] = None

    @field_validator('type')
    @classmethod
    def _check_type(cls, v):
        if v is not None:
            allowed = ('UNIVERSITY', 'ORGANIZER', 'SCHOOL', 'OTHER')
            if v not in allowed:
                raise ValueError(f"type must be one of {allowed}")
        return v


class OrganizationResponse(OrganizationBase):
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)