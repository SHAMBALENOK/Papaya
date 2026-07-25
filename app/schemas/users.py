from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID


class UserBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    surname: str
    email: EmailStr
    isActive: bool

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        # клиент шлёт id: '' — превращаем в None, чтобы не падать на валидации UUID
        return None if v == '' or v is None else v


class UserCreate(UserBase):
    password: str


class UserUpdate(UserBase):
    gender: Optional[str] = None
    bday: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    role: str


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