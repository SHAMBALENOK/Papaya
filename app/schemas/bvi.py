"""Схемы связи «университет даёт БВИ за олимпиаду».

Минимальный контракт без «заделов на будущее»: пара id + статус заявки.
Факультеты, образовательные программы и прочие условия привязки в схеме
не заложены намеренно — концепция Papaya их не описывает.

Жизненный цикл связи — три административных действия, а не «любая смена
статуса»:

```text
нет связи  →  PENDING        (заявка представителя)
PENDING    →  CONFIRMED      (подтверждение администратора)
PENDING    →  связь удалена  (отклонение заявки)
CONFIRMED  →  связь удалена  (отзыв подтверждения)
```

Возврат ``CONFIRMED → PENDING`` в модели отсутствует: это не «состояние
заявки», а отзыв публичного факта, и выражается удалением связи. Иначе после
отзыва остаётся запись, которая в публичном каталоге не показывается, а в
очереди модерации висит как неподтверждённая — то есть ни то, ни другое.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

BVI_STATUSES = ('PENDING', 'CONFIRMED')

#: Действия администратора над заявкой.
#:
#: ``confirm`` — подтвердить заявку (``PENDING`` → ``CONFIRMED``);
#: ``reject``  — отклонить заявку, связь удаляется;
#: ``revoke``  — отозвать подтверждение, связь удаляется.
BVI_ACTIONS = ('confirm', 'reject', 'revoke')


class BviLinkRequest(BaseModel):
    """Заявка: представитель университета заявляет, что вуз даёт БВИ.

    Передаётся только ``olympiad_id``: университет берётся из контекста
    (path-параметр), чтобы клиент не мог подать заявку «за чужой» вуз.
    """

    olympiad_id: UUID


class BviModerationRequest(BaseModel):
    """Административное действие над заявкой."""

    action: str

    @field_validator('action')
    @classmethod
    def validated_action(cls, v):
        if v not in BVI_ACTIONS:
            raise ValueError('action must be one of ' + ', '.join(BVI_ACTIONS))
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


class BviModerationResult(BaseModel):
    """Результат административного действия.

    ``result`` различает «статус изменён» и «связь удалена»: отклонение и отзыв
    не оставляют записи, и клиенту нужно знать, что произошло, а не угадывать
    по пустому ответу.
    """

    result: str
    university_id: UUID
    olympiad_id: UUID
    status: Optional[str] = None

    @field_validator('result')
    @classmethod
    def validated_result(cls, v):
        if v not in ('CONFIRMED', 'removed'):
            raise ValueError('result must be CONFIRMED or removed')
        return v


class BviOlympiadItem(BaseModel):
    """Олимпиада в списке «БВИ в университете».

    Публичная модель: только то, что нужно посетителю. ``name_norm``,
    ``source_doc_id``, метки времени и ``archive_reason`` — внутренние поля
    импорта и модерации, наружу не отдаются.

    ``is_historical`` отвечает на вопрос, ради которого список и смотрит:
    даёт ли университет БВИ за эту олимпиаду сейчас. Для подтверждённой связи
    с архивной олимпиадой это ``true``, и интерфейс показывает «Архивная
    олимпиада · Историческая связь» вместо «БВИ».
    """

    id: str | None = None
    name: str | None = None
    description: str | None = None
    official_url: str | None = None
    preview_image: str | None = None
    image: str | None = None
    source_url: str | None = None
    status: str | None = None
    bvi_status: str | None = None
    is_historical: bool = False


class BviOlympiadsResponse(BaseModel):
    olympiads: List[BviOlympiadItem]


class BviUniversityItem(BaseModel):
    """Университет в списке «даёт БВИ за олимпиаду»."""

    id: str | None = None
    name: str | None = None
    short_name: str | None = None
    description: str | None = None
    website: str | None = None
    preview_image: str | None = None
    image: str | None = None
    bvi_status: str | None = None
    is_historical: bool = False


class BviUniversitiesResponse(BaseModel):
    universities: List[BviUniversityItem]
