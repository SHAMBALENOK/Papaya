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
    isActive: bool

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        # клиент шлёт id: '' — превращаем в None, чтобы не падать на валидации UUID
        return None if v == '' or v is None else v



class EventCreate(EventBase):
    owner: str
    createdAt: datetime
    updatedAt: datetime

class EventUpdate(EventBase):
    createdAt: datetime
    updatedAt: datetime

class EventResponse(EventBase):
    ...

    class Config:
        from_attributes = True