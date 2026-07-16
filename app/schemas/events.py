from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class EventBase(BaseModel):
    id: str
    name: str
    disc: Optional[str] = None
    preview_picture: Optional[str] = None
    picture: Optional[str] = None
    isActive: bool



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