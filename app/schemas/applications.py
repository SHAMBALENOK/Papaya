"""Схемы заявок на роль представителя вуза (ТЗ §3.4)."""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

APPLICATION_STATUSES = ('PENDING', 'APPROVED', 'REJECTED')
APPLICATION_DECISIONS = ('APPROVED', 'REJECTED')


class ApplicationCreate(BaseModel):
    """Заявка подаётся от имени текущего пользователя на конкретный вуз."""

    university_id: UUID
    motivation: Optional[str] = None


class ApplicationDecision(BaseModel):
    decision: str
    note: Optional[str] = None


class ApplicationItem(BaseModel):
    id: str | None = None
    user_id: str | None = None
    university_id: str | None = None
    motivation: str | None = None
    status: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    decision_note: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    # Кто подал заявку и в какой вуз: администратор решает по человеку и вузу,
    # и по одному идентификатору решать не по чему.
    applicant_name: str | None = None
    applicant_email: str | None = None
    university_name: str | None = None
    university_short_name: str | None = None


class ApplicationsResponse(BaseModel):
    applications: List[ApplicationItem]
    total: int = 0
