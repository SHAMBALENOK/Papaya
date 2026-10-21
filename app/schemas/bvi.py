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

from datetime import date, datetime
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

#: Виды льготы (ТЗ §4.3).
BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')

#: Статусы проверки связи администрацией Papaya (ТЗ §7.1). Отдельная от
#: статуса заявки характеристика: заявка может быть подтверждена, но сведения
#: ещё не проверены.
VERIFICATION_STATUSES = ('unverified', 'verified', 'rejected')


class BviLinkRequest(BaseModel):
    """Заявка: представитель университета заявляет, что вуз даёт БВИ.

    Передаётся только ``olympiad_id``: университет берётся из контекста
    (path-параметр), чтобы клиент не мог подать заявку «за чужой» вуз.
    """

    olympiad_id: UUID


class BenefitRuleUpdate(BaseModel):
    """Правка правила льготы (ТЗ §4.3, §7.1).

    Все поля необязательные: меняются только переданные. ``benefit_type`` и
    ``verification_status`` валидируются по спискам допустимых значений уже в
    слое данных; пустая схема тоже недопустима — нечего менять.
    """

    benefit_type: Optional[str] = None
    result_requirement: Optional[str] = None
    subject: Optional[str] = None
    programs: Optional[List[str]] = None
    extra_requirements: Optional[str] = None
    source_url: Optional[str] = None
    # Дата, до которой правило действует: в БД это колонка DATE, поэтому и
    # контракт — дата. Дата с временем в колонку DATE не пишется.
    valid_until: Optional[date] = None
    verification_status: Optional[str] = None
    # Необязательное пояснение к правке — попадает в историю версий.
    reason: Optional[str] = None

    @field_validator('benefit_type')
    @classmethod
    def _check_benefit_type(cls, v):
        if v is not None and v not in BENEFIT_TYPES:
            raise ValueError('benefit_type must be one of ' + ', '.join(BENEFIT_TYPES))
        return v

    @field_validator('verification_status')
    @classmethod
    def _check_verification(cls, v):
        if v is not None and v not in VERIFICATION_STATUSES:
            raise ValueError(
                'verification_status must be one of '
                + ', '.join(VERIFICATION_STATUSES)
            )
        return v


class UniversityConfirmationRequest(BaseModel):
    """Отметка подтверждения правила со стороны вуза."""

    confirmed: bool = True


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
    """Связь БВИ в ответе на заявку представителя.

    Минимальный публичный контракт: пара id, статус и актуальность олимпиады.
    ``createdBy`` / ``confirmedBy`` / ``createdAt`` / ``updatedAt`` — служебные
    поля модерации, пользователю они ничего не дают, поэтому наружу не
    отдаются: по заявке достаточно понимать, что она создана и в каком статусе.
    """

    id: Optional[UUID] = None
    university_id: UUID
    olympiad_id: UUID
    status: str = 'PENDING'
    # Актуальна ли олимпиада: по архивной новых заявок не бывает, но
    # подтверждённая историческая связь остаётся в списке.
    is_historical: bool = False

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
    # Поля правила льготы: вид льготы, требуемый результат, предмет и статус
    # проверки. Последнее — независимая характеристика: непроверенная связь
    # видна в каталоге с пометкой «Не проверено Papaya».
    benefit_type: str | None = None
    result_requirement: str | None = None
    subject: str | None = None
    programs: List[str] | None = None
    extra_requirements: str | None = None
    source_url_rule: str | None = None
    valid_until: str | None = None
    verification_status: str | None = None
    university_confirmed: bool = False
    is_historical_note: str | None = None


class BviOlympiadsResponse(BaseModel):
    olympiads: List[BviOlympiadItem]
    total: int = 0


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
    benefit_type: str | None = None
    result_requirement: str | None = None
    subject: str | None = None
    verification_status: str | None = None
    university_confirmed: bool = False


class BviUniversitiesResponse(BaseModel):
    universities: List[BviUniversityItem]
    total: int = 0


class BenefitRuleVersionItem(BaseModel):
    """Версия правила льготы в истории (ТЗ §8)."""

    id: str | None = None
    link_id: str | None = None
    version: int | None = None
    snapshot: dict | None = None
    changed_by: str | None = None
    changed_at: str | None = None
    reason: str | None = None
    verification_status: str | None = None
    source_doc_id: str | None = None
    is_rollback: bool = False


class BenefitRuleVersionsResponse(BaseModel):
    versions: List[BenefitRuleVersionItem]


class BenefitRuleUpdateResponse(BaseModel):
    """Результат правки правила: текущее состояние и номер версии."""

    rule: dict
    version: int | None = None
    changed: bool = False


class BenefitRuleListItem(BaseModel):
    """Строка списка правил вуза (ТЗ §4.5): фильтры и модерация."""

    id: str | None = None
    university_id: str | None = None
    olympiad_id: str | None = None
    olympiad_name: str | None = None
    status: str | None = None
    benefit_type: str | None = None
    result_requirement: str | None = None
    subject: str | None = None
    programs: List[str] | None = None
    source_url: str | None = None
    valid_until: str | None = None
    verification_status: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    university_confirmed: bool = False
    university_confirmed_at: str | None = None
    olympiad_status: str | None = None
    createdAt: str | None = None


class BenefitRulesResponse(BaseModel):
    rules: List[BenefitRuleListItem]
    total: int = 0

