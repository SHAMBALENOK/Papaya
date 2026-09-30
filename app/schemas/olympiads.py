"""Схемы каталога олимпиад.

Олимпиада — единая сущность каталога, независимая от года. Схема записи не
принимает ``status``: актуальность определяется импортом РСОШ и архивированием
(см. ``app/rsosh/persist.py``) либо администратором через отдельный маршрут.

Публичная карточка и ответ админских маршрутов различаются составом полей:
``source_doc_id`` — внутренняя ссылка на загруженный документ, и в публичном
ответе её нет (пользователю достаточно ``GET /olympiads/{id}/source``).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.urls import ExternalUrl

OLYMPIAD_STATUSES = ('PUBLISHED', 'ARCHIVED')

# Причины архивирования: см. app/models/olympiads.py.
ARCHIVE_REASONS = ('RSOSH_ABSENT', 'MANUAL')


class OlympiadBase(BaseModel):
    id: Optional[UUID] = None
    name: str
    name_norm: Optional[str] = None
    description: Optional[str] = None
    official_url: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None
    source_url: Optional[ExternalUrl] = None
    status: str = 'PUBLISHED'
    archive_reason: Optional[str] = None

    @field_validator('id', mode='before')
    @classmethod
    def _empty_id_to_none(cls, v):
        return None if v == '' or v is None else v

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v not in OLYMPIAD_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(OLYMPIAD_STATUSES))
        return v

    @field_validator('archive_reason')
    @classmethod
    def _check_archive_reason(cls, v):
        if v is not None and v not in ARCHIVE_REASONS:
            raise ValueError('archive_reason must be one of ' + ', '.join(ARCHIVE_REASONS))
        return v


class OlympiadCreate(BaseModel):
    """Создание олимпиады вручную (администратором).

    Единственный автоматический способ добавить олимпиаду — импорт документов
    РСОШ; ручное создание остаётся резервным путём для редких случаев.
    """

    name: str
    description: Optional[str] = None
    official_url: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None
    source_url: Optional[ExternalUrl] = None

    @field_validator('name')
    @classmethod
    def _name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError('name is required')
        return v.strip()


class OlympiadUpdate(BaseModel):
    """Частичное обновление олимпиады. Все поля опциональны.

    ``status`` и ``archive_reason`` здесь нет намеренно: актуальность и причина
    архива — решение импорта РСОШ или администратора, и меняются они через
    ``POST /api/v1/admin/archive_olympiad/{id}``, где причина выставляется
    вместе со статусом. Через эту схему нельзя сделать запись актуальной
    «просто потому, что её вернули из архива».
    """

    name: Optional[str] = None
    description: Optional[str] = None
    official_url: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None
    source_url: Optional[ExternalUrl] = None

    @field_validator('name')
    @classmethod
    def _name_not_blank(cls, v):
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError('name is required')
        return v.strip()


class OlympiadResponse(OlympiadBase):
    """Ответ админских маршрутов (создание, правка, архив).

    В отличие от публичной карточки содержит ``source_doc_id``: администратор
    должен видеть, из какого документа взялась запись. Публично этот
    идентификатор не отдаётся — для пользователя есть ``/olympiads/{id}/source``.
    """

    source_doc_id: Optional[UUID] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OlympiadPublicResponse(BaseModel):
    """Публичная карточка олимпиады: только пользовательские поля.

    Отдельная схема, а не наследник ``OlympiadBase``, потому что базовая нужна
    админским маршрутам (создание, правка, архив) и отдаёт служебные данные.
    Наружу они не выходят:

    - ``name_norm`` — служебное нормализованное имя для дедупликации при импорте;
    - ``source_doc_id`` — внутренняя ссылка на загруженный документ (для
      пользователя есть ``GET /olympiads/{id}/source``);
    - ``createdAt`` / ``updatedAt`` — служебные метки времени;
    - ``archive_reason`` — техническое значение ``RSOSH_ABSENT`` / ``MANUAL``,
      пользователю оно ничего не объясняет. Про архив пользователь узнаёт по
      ``status`` и читает понятный текст в интерфейсе.
    """

    id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    official_url: Optional[ExternalUrl] = None
    preview_image: Optional[ExternalUrl] = None
    image: Optional[ExternalUrl] = None
    source_url: Optional[ExternalUrl] = None
    status: str = 'PUBLISHED'

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v not in OLYMPIAD_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(OLYMPIAD_STATUSES))
        return v

    @property
    def is_archived(self) -> bool:
        """Олимпиада вне актуального каталога.

        Производное поле для интерфейса: карточке нужно понимать, показывать ли
        предупреждение об архиве, а разбирать ``status`` в шаблоне — это
        дублирование правил на клиенте.
        """
        return self.status == 'ARCHIVED'

    model_config = ConfigDict(from_attributes=True)
