from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    id: str
    name: str
    surname: str
    email: EmailStr
    isActive: bool


class UserCreate(UserBase):
    password: str
    createdAt: datetime
    updatedAt: datetime

class UserUpdate(BaseModel):
    gender: Optional[str] = None
    bday: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    role: str
    updatedAt: datetime

class UserResponse(UserBase):
    gender: Optional[str] = None
    bday: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True