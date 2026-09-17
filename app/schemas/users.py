from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime

class UserBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    surname: str
    email: EmailStr
    isActive: bool = True

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

class UserCreate(BaseModel):
    """Регистрация.

    Контракт: id, isActive, role, createdAt и updatedAt задаёт сервер.
    Пароль принимается только на входе и не возвращается в ответах.
    """
    name: str
    surname: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    """Логин: достаточно email и пароля."""
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    """Частичное обновление профиля. role и isActive нельзя менять через этот endpoint."""
    name: Optional[str] = None
    surname: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    bday: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None

class UserResponse(UserBase):
    gender: Optional[str] = None
    bday: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    role: str = 'USER'
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True
