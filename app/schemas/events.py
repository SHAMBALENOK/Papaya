from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
from uuid import UUID

class EventBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    disc: Optional[str] = None
    preview_picture: Optional[str] = None
    picture: Optional[str] = None
    isActive: bool = True

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v


class EventCreate(BaseModel):
    """Создание события.

    Контракт: id, owner, isActive, createdAt и updatedAt задаёт сервер.
    Поля name/disc/preview_picture/picture приходят от клиента.
    """
    name: str
    disc: Optional[str] = None
    preview_picture: Optional[str] = None
    picture: Optional[str] = None

class EventUpdate(BaseModel):
    """Частичное обновление события. Все поля опциональны."""
    name: Optional[str] = None
    disc: Optional[str] = None
    preview_picture: Optional[str] = None
    picture: Optional[str] = None

class EventResponse(EventBase):
    owner: Optional[UUID] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True
