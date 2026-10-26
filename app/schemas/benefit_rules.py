"""Схемы правила льготы (ТЗ §4.3, §7, §8, §9).

Правило льготы — отдельная сущность: университет + олимпиада + (сезон,
профиль) + вид льготы + требуемый результат + предмет + программы + доп.
условия + документ + ссылка на источник + статусы.

Жизненный цикл (публикационное состояние ``status``):

```text
draft      →  published   (представитель/администратор публикует)
published  →  draft       (снять с публикации)
published  →  archived    (правило больше не действует; история сохраняется)
archived   →  draft       (вернуть из архива для правки)
draft      →  удалено     (черновик можно удалить физически)
```

Проверка Papaya (``verification_status``) — независимая характеристика:
``unverified`` / ``verified`` / ``rejected``. Она сбрасывается в
``unverified`` при любом содержательном изменении и при откате версии.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.urls import ExternalUrl

BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')
VERIFICATION_STATUSES = ('unverified', 'verified', 'rejected')
RULE_STATUSES = ('draft', 'published', 'archived')


def _check_benefit_type(value):
    if value is not None and value not in BENEFIT_TYPES:
        raise ValueError('benefit_type must be one of ' + ', '.join(BENEFIT_TYPES))
    return value


def _check_verification(value):
    if value is not None and value not in VERIFICATION_STATUSES:
        raise ValueError(
            'verification_status must be one of ' + ', '.join(VERIFICATION_STATUSES)
        )
    return value


class BenefitRuleCreate(BaseModel):
    """Создание правила льготы представителем своего вуза или администратором.

    Университет берётся из пути: клиент не может завести правило «за чужой»
    вуз. ``program_ids`` — идентификаторы существующих программ этого вуза
    (названия текстом не принимаются: программа уже есть в БД).
    ``publish=true`` сразу публикует правило (оно появится в каталоге с
    пометкой «Не проверено Papaya»). ``source_doc_id`` и
    ``verification_status`` учитываются только у администратора.
    """

    olympiad_id: UUID
    season_id: Optional[UUID] = None
    profile_id: Optional[UUID] = None
    benefit_type: str = 'BVI'
    result_requirement: Optional[str] = None
    subject: Optional[str] = None
    program_ids: List[UUID] = []
    extra_requirements: Optional[str] = None
    source_url: Optional[ExternalUrl] = None
    valid_until: Optional[date] = None
    source_doc_id: Optional[UUID] = None
    verification_status: Optional[str] = None
    publish: bool = False
    reason: Optional[str] = None

    _bt = field_validator('benefit_type')(_check_benefit_type)
    _vs = field_validator('verification_status')(_check_verification)


class BenefitRuleUpdate(BaseModel):
    """Частичная правка правила: меняются только переданные поля.

    ``expected_version`` — оптимистическая блокировка: если правило уже
    изменено кем-то другим, сервер отвечает 409, а не перезаписывает правки.
    ``season_id``/``profile_id`` можно обнулить, передав ``null`` явно.
    """

    model_config = ConfigDict(extra='forbid')

    season_id: Optional[UUID] = None
    profile_id: Optional[UUID] = None
    benefit_type: Optional[str] = None
    result_requirement: Optional[str] = None
    subject: Optional[str] = None
    program_ids: Optional[List[UUID]] = None
    extra_requirements: Optional[str] = None
    source_url: Optional[ExternalUrl] = None
    valid_until: Optional[date] = None
    source_doc_id: Optional[UUID] = None
    verification_status: Optional[str] = None
    verification_note: Optional[str] = None
    reason: Optional[str] = None
    expected_version: Optional[int] = None

    _bt = field_validator('benefit_type')(_check_benefit_type)
    _vs = field_validator('verification_status')(_check_verification)


class BenefitRuleStatusRequest(BaseModel):
    """Смена публикационного состояния: ``draft`` / ``published`` / ``archived``."""

    status: str
    reason: Optional[str] = None
    expected_version: Optional[int] = None

    @field_validator('status')
    @classmethod
    def _check_status(cls, value):
        if value not in RULE_STATUSES:
            raise ValueError('status must be one of ' + ', '.join(RULE_STATUSES))
        return value


class BenefitRuleVerificationRequest(BaseModel):
    """Решение проверки Papaya. При ``rejected`` причина обязательна."""

    status: str
    note: Optional[str] = None
    expected_version: Optional[int] = None

    _vs = field_validator('status')(_check_verification)


class BenefitRuleRollbackRequest(BaseModel):
    version: int
    reason: Optional[str] = None
    expected_version: Optional[int] = None


class UniversityConfirmationRequest(BaseModel):
    """Подтверждение со стороны вуза — не проверка Papaya."""

    confirmed: bool = True


class RuleSeasonInfo(BaseModel):
    id: str | None = None
    year: int | None = None
    label: str | None = None
    state: str | None = None


class RuleProfileInfo(BaseModel):
    id: str | None = None
    name: str | None = None
    subject: str | None = None


class RuleDocumentInfo(BaseModel):
    id: str | None = None
    name: str | None = None
    has_file: bool = False
    availability: str | None = None
    source_url: str | None = None


class RuleProgramInfo(BaseModel):
    id: str | None = None
    name: str | None = None


class BenefitRuleItem(BaseModel):
    """Правило льготы со связанными сущностями (общая форма ответа).

    Служебные поля (``source_meta``, ``dedup_key``) наружу не отдаются.
    """

    model_config = ConfigDict(extra='ignore')

    id: str | None = None
    university_id: str | None = None
    university_name: str | None = None
    university_short_name: str | None = None
    olympiad_id: str | None = None
    olympiad_name: str | None = None
    olympiad_status: str | None = None
    is_historical: bool = False
    season_id: str | None = None
    season: RuleSeasonInfo | None = None
    profile_id: str | None = None
    profile: RuleProfileInfo | None = None
    status: str | None = None
    benefit_type: str | None = None
    result_requirement: str | None = None
    subject: str | None = None
    programs: List[RuleProgramInfo] = []
    program_ids: List[str] = []
    extra_requirements: str | None = None
    source_url: str | None = None
    source_doc_id: str | None = None
    document: RuleDocumentInfo | None = None
    valid_until: str | None = None
    verification_status: str | None = None
    verified_at: str | None = None
    verification_note: str | None = None
    university_confirmed: bool = False
    university_confirmed_at: str | None = None
    version: int = 0
    published_at: str | None = None
    createdBy: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class BenefitRulesResponse(BaseModel):
    rules: List[BenefitRuleItem]
    total: int = 0


class FacetValue(BaseModel):
    value: str | None = None
    count: int = 0


class FacetProgram(BaseModel):
    id: str | None = None
    name: str | None = None
    count: int = 0


class FacetSeason(BaseModel):
    id: str | None = None
    year: int | None = None
    label: str | None = None
    state: str | None = None
    count: int = 0


class BenefitRuleFacets(BaseModel):
    """Значения фильтров, посчитанные СУБД по всем правилам под областью."""

    benefit_types: List[FacetValue] = []
    subjects: List[FacetValue] = []
    programs: List[FacetProgram] = []
    seasons: List[FacetSeason] = []


class OlympiadWithRules(BaseModel):
    """Олимпиада на странице университета вместе с её правилами."""

    model_config = ConfigDict(extra='ignore')

    id: str | None = None
    name: str | None = None
    description: str | None = None
    official_url: str | None = None
    organizer: str | None = None
    preview_image: str | None = None
    image: str | None = None
    status: str | None = None
    is_historical: bool = False
    rules: List[BenefitRuleItem] = []


class OlympiadsWithRulesResponse(BaseModel):
    olympiads: List[OlympiadWithRules]
    total: int = 0


class UniversityWithRules(BaseModel):
    """Университет на странице олимпиады вместе с его правилами."""

    model_config = ConfigDict(extra='ignore')

    id: str | None = None
    name: str | None = None
    short_name: str | None = None
    description: str | None = None
    website: str | None = None
    preview_image: str | None = None
    image: str | None = None
    is_historical: bool = False
    rules: List[BenefitRuleItem] = []


class UniversitiesWithRulesResponse(BaseModel):
    universities: List[UniversityWithRules]
    total: int = 0


class BenefitRuleVersionItem(BaseModel):
    id: str | None = None
    rule_id: str | None = None
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
    current_version: int = 0
