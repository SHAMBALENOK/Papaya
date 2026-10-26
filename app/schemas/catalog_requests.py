"""Схемы запросов представителя о пополнении каталога."""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

CATALOG_REQUEST_KINDS = ('olympiad', 'season', 'profile', 'other')
CATALOG_REQUEST_STATUSES = ('open', 'resolved', 'rejected')


class CatalogRequestCreate(BaseModel):
    kind: str = 'olympiad'
    olympiad_id: Optional[UUID] = None
    text: str

    @field_validator('kind')
    @classmethod
    def _check_kind(cls, value):
        if value not in CATALOG_REQUEST_KINDS:
            raise ValueError('kind must be one of ' + ', '.join(CATALOG_REQUEST_KINDS))
        return value

    @field_validator('text')
    @classmethod
    def _text_not_blank(cls, value):
        if not value or not value.strip():
            raise ValueError('text is required')
        if len(value) > 4000:
            raise ValueError('text is too long')
        return value.strip()


class CatalogRequestResolve(BaseModel):
    status: str
    note: Optional[str] = None

    @field_validator('status')
    @classmethod
    def _check_status(cls, value):
        if value not in CATALOG_REQUEST_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(CATALOG_REQUEST_STATUSES))
        return value


class CatalogRequestItem(BaseModel):
    id: str | None = None
    university_id: str | None = None
    university_name: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    kind: str | None = None
    olympiad_id: str | None = None
    olympiad_name: str | None = None
    text: str | None = None
    status: str | None = None
    admin_note: str | None = None
    resolved_at: str | None = None
    createdAt: str | None = None


class CatalogRequestsResponse(BaseModel):
    requests: List[CatalogRequestItem]
    total: int = 0
