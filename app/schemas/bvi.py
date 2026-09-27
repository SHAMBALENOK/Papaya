"""Схемы связи «университет даёт БВИ за олимпиаду».

Минимальный контракт без «заделов на будущее»: пара id + статус заявки.
Факультеты, образовательные программы и прочие условия привязки в схеме
не заложены намеренно — концепция Papaya их не описывает.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

BVI_STATUSES = ('PENDING', 'CONFIRMED')


class BviLinkRequest(BaseModel):
    """Заявка: представитель университета заявляет, что вуз даёт БВИ.

    Передаётся только ``olympiad_id``: университет берётся из контекста
    (path-параметр), чтобы клиент не мог подать заявку «за чужой» вуз.
    """

    olympiad_id: UUID


class BviStatusUpdate(BaseModel):
    """Смена статуса связи администратором (подтверждение/снятие)."""

    status: str

    @field_validator('status')
    @classmethod
    def validated_status(cls, v):
        if v not in BVI_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(BVI_STATUSES))
        return v


class BviLinkResponse(BaseModel):
    """Связь БВИ в ответе API."""

    id: Optional[UUID] = None
    university_id: UUID
    olympiad_id: UUID
    status: str = 'PENDING'
    createdBy: Optional[UUID] = None
    confirmedBy: Optional[UUID] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
