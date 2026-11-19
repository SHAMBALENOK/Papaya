"""API правил льгот.

Публичная часть каталога отдаёт опубликованные правила, включая непроверенные
(они помечаются предупреждением «Не проверено Papaya»); отклонённые и
черновики не видны. Представитель может создавать и править правила своего
университета, но не может подтверждать их: ``verified`` выставляется
исключительно администратором через ``/verify``. Любая содержательная правка
проверенного правила снимает проверку.

Правило больше не хранит свободный текст условий: тип льготы, требуемый
результат и требование ЕГЭ — структурированные поля.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from app import database
from app.core import deps
from app.models.benefits import (
    BENEFIT_TYPES,
    REQUIRED_RESULT_TYPES,
    VERIFICATION_STATUSES,
)

benefits_page = APIRouter(prefix='/benefits', tags=['benefits'])
benefit_rules_page = APIRouter(prefix='/benefit-rules', tags=['benefits'])
university_benefits_page = APIRouter(tags=['benefits'])
olympiad_benefits_page = APIRouter(tags=['benefits'])
admin_benefits_page = APIRouter(prefix='/admin/benefits', tags=['benefits'])

logger = logging.getLogger('papaya.benefits')

MAX_PAGE_SIZE = 200


def _check_benefit_type(v):
    if v is None:
        return v
    normalized = database.benefits.normalize_benefit_type(v)
    if normalized not in BENEFIT_TYPES:
        raise ValueError('benefit_type must be one of ' + ', '.join(BENEFIT_TYPES))
    return normalized


def _check_result_type(v):
    """Требуемый результат — только структурированное значение.

    Свободный текст вида «победитель или призёр» раньше молча превращался в
    ``WINNER_OR_PRIZE`` алиасом миграции. На границе API это недопустимо:
    клиент должен присылать одно из ``REQUIRED_RESULT_TYPES``, иначе ``422``.
    """
    if v is None:
        return v
    if isinstance(v, str) and v.strip().upper() in REQUIRED_RESULT_TYPES:
        return v.strip().upper()
    raise ValueError(
        'required_result_type must be one of '
        + ', '.join(REQUIRED_RESULT_TYPES)
    )


def _check_status(v):
    if v is not None and v not in VERIFICATION_STATUSES:
        raise ValueError(
            'verification_status must be one of ' + ', '.join(VERIFICATION_STATUSES)
        )
    return v


class EgeRequirement(BaseModel):
    """Необязательное подтверждение результата ЕГЭ."""

    subject: str
    min_score: int | None = Field(default=None, ge=0, le=100)

    @field_validator('subject')
    @classmethod
    def _check_subject(cls, v):
        v = (v or '').strip()
        if not v:
            raise ValueError('subject is required')
        return v


class BenefitCreate(BaseModel):
    olympiad_id: uuid.UUID
    season_id: uuid.UUID
    profile_id: uuid.UUID
    benefit_type: str = 'BVI'
    required_result_type: str
    doc_id: uuid.UUID
    ege_requirement: EgeRequirement | None = None
    is_published: bool | None = None
    # Подтверждение приходит только от администратора отдельным действием.
    verification_status: str | None = None

    _benefit_type = field_validator('benefit_type')(_check_benefit_type)
    _required_result_type = field_validator('required_result_type')(_check_result_type)
    _verification_status = field_validator('verification_status')(_check_status)


class BenefitUpdate(BaseModel):
    version: int | None = Field(default=None, ge=1)
    season_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    benefit_type: str | None = None
    required_result_type: str | None = None
    doc_id: uuid.UUID | None = None
    ege_requirement: EgeRequirement | None = None
    verification_status: str | None = None
    is_published: bool | None = None
    needs_review: bool | None = None
    change_reason: str | None = None

    _benefit_type = field_validator('benefit_type')(_check_benefit_type)
    _required_result_type = field_validator('required_result_type')(_check_result_type)
    _verification_status = field_validator('verification_status')(_check_status)


class StatusChange(BaseModel):
    status: str
    reason: str | None = None

    @field_validator('status')
    @classmethod
    def _check_status(cls, v):
        if v not in VERIFICATION_STATUSES:
            raise ValueError(
                'status must be one of ' + ', '.join(VERIFICATION_STATUSES)
            )
        return v


class RejectRequest(BaseModel):
    """Отклонение правила: причина обязательна.

    Отдельная модель, а не ``StatusChange``: отказ — это не «смена статуса на
    rejected», а действие с объяснением, которое увидит автор правила. Клиенту
    не нужно присылать ``status``, достаточно непустой причины. Поле объявлено
    необязательным, чтобы пустой запрос получал понятный ``422`` от обработчика,
    а не техническое «Field required» от валидатора.
    """

    reason: str | None = None


class RollbackRequest(BaseModel):
    version: int = Field(ge=1, description='Номер восстанавливаемой версии')
    expected_version: int | None = Field(
        default=None,
        ge=1,
        description='Текущая версия правила, которую видел клиент',
    )


async def _ensure_manage(rule, current_user):
    if not deps.can_manage_university(current_user, rule['university_id']):
        raise HTTPException(
            status_code=403, detail='You can only manage your own university'
        )


async def _get_rule_or_404(rule_id, *, public_only=False):
    rule = await database.benefits.get_rule(rule_id, public_only=public_only)
    if not rule:
        raise HTTPException(status_code=404, detail='Benefit rule not found')
    return rule


async def _validate_refs(university_id, data, current_user, existing=None):
    """Проверить согласованность связей правила.

    Внешние ключи в БД не выражают эти инварианты: ``season_id`` может
    относиться к другой олимпиаде, ``profile_id`` — к другому сезону, а
    документ — к другому университету.
    """
    olympiad_id = data.get('olympiad_id') or (existing or {}).get('olympiad_id')
    season_id = data.get('season_id', (existing or {}).get('season_id'))
    profile_id = data.get('profile_id', (existing or {}).get('profile_id'))

    if olympiad_id:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=404, detail='Olympiad not found')
        # Архивированная олимпиада не принимает новых правил, но уже
        # существующее правило остаётся редактируемым.
        if existing is None and olympiad.get('status') == 'ARCHIVED':
            raise HTTPException(
                status_code=422,
                detail='Olympiad is archived and accepts no new benefit rules',
            )

    if existing is None:
        if not season_id:
            raise HTTPException(
                status_code=422, detail='Season is required for a benefit rule'
            )
        if not profile_id:
            raise HTTPException(
                status_code=422, detail='Profile is required for a benefit rule'
            )

    if season_id:
        season = await database.seasons.get_season(season_id)
        if not season:
            raise HTTPException(status_code=404, detail='Season not found')
        if olympiad_id and str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(
                status_code=422,
                detail='Season does not belong to the selected olympiad',
            )

    if profile_id:
        if not season_id:
            raise HTTPException(
                status_code=422, detail='Profile requires a season'
            )
        profile = await database.seasons.get_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail='Profile not found')
        if str(profile.get('season_id')) != str(season_id):
            raise HTTPException(
                status_code=422,
                detail='Profile does not belong to the selected season',
            )

    doc_id = data.get('doc_id', (existing or {}).get('doc_id'))
    if doc_id:
        doc = await database.docs.get_doc(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        if str(doc.get('university_id') or '') != str(university_id):
            raise HTTPException(
                status_code=422,
                detail='Document must belong to the same university',
            )
        if doc.get('type') != 'UNIVERSITY_ORDER':
            raise HTTPException(
                status_code=422,
                detail='Only a university order can be the basis of a benefit',
            )
    elif existing is None:
        raise HTTPException(
            status_code=422, detail='University document is required'
        )


def _page_params(limit, offset):
    if limit is None:
        limit = 50
    return min(max(1, int(limit)), MAX_PAGE_SIZE), max(0, int(offset or 0))


def _list_kwargs(
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    season_id=None,
    profile_id=None,
    level=None,
    verification_status=None,
    needs_review=None,
    search=None,
):
    return {
        'university_id': university_id,
        'olympiad_id': olympiad_id,
        'benefit_type': benefit_type,
        'season_id': season_id,
        'profile_id': profile_id,
        'level': level,
        'verification_status': verification_status,
        'needs_review': needs_review,
        'search': search,
    }


async def _list_handler(limit=50, offset=0, **filters):
    limit, offset = _page_params(limit, offset)
    rules, total = await database.benefits.list_rules(
        public_only=True, limit=limit, offset=offset, **filters
    )
    return {
        'rules': rules,
        'total': total,
        'limit': limit,
        'offset': offset,
    }


# ---------------------------------------------------------------- public list


def _public_query_params():
    """Повторяющийся набор query-параметров публичного каталога."""

    return {
        'university_id': Query(default=None),
        'olympiad_id': Query(default=None),
        'benefit_type': Query(default=None),
        'season_id': Query(default=None),
        'profile_id': Query(default=None),
        'level': Query(default=None, pattern='^[123]$'),
        'search': Query(default=None),
        'limit': Query(default=50, ge=1, le=MAX_PAGE_SIZE),
        'offset': Query(default=0, ge=0),
    }


@benefits_page.get('')
async def list_benefits(
    university_id: uuid.UUID | None = None,
    olympiad_id: uuid.UUID | None = None,
    benefit_type: str | None = None,
    season_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    level: str | None = Query(default=None, pattern='^[123]$'),
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        return await _list_handler(
            limit=limit,
            offset=offset,
            **_list_kwargs(
                university_id=university_id,
                olympiad_id=olympiad_id,
                benefit_type=benefit_type,
                season_id=season_id,
                profile_id=profile_id,
                level=level,
                search=search,
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.get('')
async def list_benefit_rules(
    university_id: uuid.UUID | None = None,
    olympiad_id: uuid.UUID | None = None,
    benefit_type: str | None = None,
    season_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    level: str | None = Query(default=None, pattern='^[123]$'),
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await list_benefits(
        university_id=university_id,
        olympiad_id=olympiad_id,
        benefit_type=benefit_type,
        season_id=season_id,
        profile_id=profile_id,
        level=level,
        search=search,
        limit=limit,
        offset=offset,
    )


@university_benefits_page.get('/universities/{university_id}/benefits')
async def list_university_benefits(
    university_id: uuid.UUID,
    benefit_type: str | None = None,
    olympiad_id: uuid.UUID | None = None,
    season_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    level: str | None = Query(default=None, pattern='^[123]$'),
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        return await _list_handler(
            limit=limit,
            offset=offset,
            **_list_kwargs(
                university_id=str(university_id),
                olympiad_id=olympiad_id,
                benefit_type=benefit_type,
                season_id=season_id,
                profile_id=profile_id,
                level=level,
                search=search,
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_benefits_page.get('/universities/{university_id}/benefit-rules')
async def list_university_benefit_rules(
    university_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await list_university_benefits(
        university_id, limit=limit, offset=offset
    )


@university_benefits_page.get('/universities/{university_id}/benefit-rules/manage')
async def list_managed_university_benefit_rules(
    university_id: uuid.UUID,
    verification_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(deps.require_manage_university),
):
    """Рабочий список правил своего университета, включая черновики.

    Публичный список показывает опубликованные правила (в том числе
    непроверенные). Представителю нужны ещё черновики и отклонённые правила:
    без этого он не смог бы продолжить работу над черновиком или увидеть
    причину отказа.
    """
    try:
        rules, total = await database.benefits.list_rules(
            university_id=str(university_id),
            verification_status=verification_status,
            search=search,
            needs_review=needs_review,
            public_only=False,
            limit=limit,
            offset=offset,
        )
        return {
            'rules': rules,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.get('/olympiad/{olympiad_id}')
async def list_olympiad_benefits(
    olympiad_id: uuid.UUID,
    season_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        return await _list_handler(
            limit=limit,
            offset=offset,
            **_list_kwargs(
                olympiad_id=olympiad_id,
                season_id=season_id,
                profile_id=profile_id,
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiad_benefits_page.get('/olympiads/{olympiad_id}/benefits')
async def list_olympiad_benefits_alias(
    olympiad_id: uuid.UUID,
    season_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await list_olympiad_benefits(
        olympiad_id, season_id, profile_id, limit, offset
    )


# ------------------------------------------------------------------- create


async def _create_handler(university_id, body, current_user):
    if not deps.can_manage_university(current_user, university_id):
        raise HTTPException(
            status_code=403, detail='You can only manage your own university'
        )
    data = body.model_dump()
    # Подтверждение никогда не приходит из клиента: даже если поле передали,
    # правило создаётся непроверенным.
    data.pop('verification_status', None)
    data['university_id'] = str(university_id)
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        await _validate_refs(university_id, data, current_user)
        rule = await database.benefits.create_rule(
            data, user_id=current_user['id']
        )
        await database.audit.log_action(
            'benefit_rule', rule['id'], 'create',
            user_id=current_user['id'], after=rule,
        )
        return rule
    except HTTPException:
        raise
    except database.benefits.InvalidReference as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail='Benefit rule for this university, olympiad, season and profile already exists',
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_benefits_page.post('/universities/{university_id}/benefits')
async def create_university_benefit(
    university_id: uuid.UUID,
    body: BenefitCreate,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await _create_handler(university_id, body, current_user)


@university_benefits_page.post('/universities/{university_id}/benefit-rules')
async def create_university_benefit_rule(
    university_id: uuid.UUID,
    body: BenefitCreate,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await _create_handler(university_id, body, current_user)


# ------------------------------------------------------------------- detail


async def _get_handler(rule_id, public_only=True):
    try:
        return await _get_rule_or_404(rule_id, public_only=public_only)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.get('/{rule_id}')
async def get_benefit(rule_id: uuid.UUID):
    return await _get_handler(rule_id)


@benefit_rules_page.get('/{rule_id}')
async def get_benefit_rule(rule_id: uuid.UUID):
    return await _get_handler(rule_id)


# ------------------------------------------------------------------- update


async def _update_handler(rule_id, body, current_user):
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    if 'verification_status' in body.model_fields_set:
        raise HTTPException(
            status_code=403,
            detail='Verification status is managed by Papaya administrators',
        )
    data = body.model_dump(exclude_unset=True)
    expected = data.pop('version', None)
    reason = data.pop('change_reason', None)
    try:
        await _validate_refs(
            rule['university_id'], data, current_user, existing=rule
        )
        updated = await database.benefits.update_rule(
            rule_id,
            data,
            user_id=current_user['id'],
            reason=reason,
            expected_version=expected,
        )
        if not updated:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        await database.audit.log_action(
            'benefit_rule', rule_id, 'update',
            user_id=current_user['id'], before=rule, after=updated,
        )
        return updated
    except database.benefits.InvalidReference as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except database.benefits.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.put('/{rule_id}')
async def update_benefit(
    rule_id: uuid.UUID,
    body: BenefitUpdate,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await _update_handler(rule_id, body, current_user)


@benefit_rules_page.put('/{rule_id}')
async def update_benefit_rule(
    rule_id: uuid.UUID,
    body: BenefitUpdate,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await _update_handler(rule_id, body, current_user)


@benefits_page.patch('/{rule_id}')
async def patch_benefit(
    rule_id: uuid.UUID,
    body: BenefitUpdate,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await _update_handler(rule_id, body, current_user)


@benefit_rules_page.patch('/{rule_id}')
async def patch_benefit_rule(
    rule_id: uuid.UUID,
    body: BenefitUpdate,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await _update_handler(rule_id, body, current_user)


# ------------------------------------------------------------------- status


@benefits_page.post('/{rule_id}/status')
async def change_status(
    rule_id: uuid.UUID,
    body: StatusChange,
    current_user: dict = Depends(deps.require_university_rep),
):
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    is_admin = current_user.get('role') == deps.ROLE_ADMIN
    if not is_admin and body.status != 'unverified':
        raise HTTPException(
            status_code=403,
            detail='Only admin can verify or reject a benefit rule',
        )
    if body.status == 'rejected' and not (body.reason or '').strip():
        raise HTTPException(
            status_code=422,
            detail='Rejection reason is required',
        )
    try:
        updated = await database.benefits.set_status(
            rule_id, body.status,
            user_id=current_user['id'], reason=body.reason,
            expected_version=rule['version'],
        )
        await database.audit.log_action(
            'benefit_rule', rule_id, 'status_change',
            user_id=current_user['id'], before=rule, after=updated,
        )
        return updated
    except database.benefits.InvalidReference as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except database.benefits.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.post('/{rule_id}/status')
async def change_status_rule(
    rule_id: uuid.UUID,
    body: StatusChange,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await change_status(rule_id, body, current_user)


# ------------------------------------------------------------------- verify


@benefits_page.post('/{rule_id}/verify')
async def verify_benefit(
    rule_id: uuid.UUID,
    current_user: dict = Depends(deps.require_admin),
):
    rule = await _get_rule_or_404(rule_id)
    try:
        updated = await database.benefits.set_status(
            rule_id, 'verified',
            user_id=current_user['id'], reason='verified by admin',
            expected_version=rule['version'],
        )
    except database.benefits.InvalidReference as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except database.benefits.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    await database.audit.log_action(
        'benefit_rule', rule_id, 'verify',
        user_id=current_user['id'], before=rule, after=updated,
    )
    return updated


@benefits_page.post('/{rule_id}/reject')
async def reject_benefit(
    rule_id: uuid.UUID,
    body: RejectRequest | None = None,
    current_user: dict = Depends(deps.require_admin),
):
    rule = await _get_rule_or_404(rule_id)
    reason = ((body.reason if body else '') or '').strip()
    if not reason:
        raise HTTPException(
            status_code=422,
            detail='Укажите причину отклонения',
        )
    try:
        updated = await database.benefits.set_status(
            rule_id, 'rejected', user_id=current_user['id'], reason=reason,
            expected_version=rule['version'],
        )
    except database.benefits.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    await database.audit.log_action(
        'benefit_rule', rule_id, 'reject',
        user_id=current_user['id'], before=rule, after=updated,
    )
    return updated


@benefits_page.get('/{rule_id}/manage')
async def get_managed_benefit(
    rule_id: uuid.UUID,
    current_user: dict = Depends(deps.require_university_rep),
):
    """Правило для редактирования: видно и до проверки администратором."""
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    return rule


# ----------------------------------------------------------------- versions


@benefits_page.get('/{rule_id}/versions')
async def list_versions(rule_id: uuid.UUID):
    try:
        await _get_rule_or_404(rule_id, public_only=True)
        versions = await database.benefits.list_versions(rule_id)
        return {'versions': versions}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.get('/{rule_id}/versions/manage')
async def list_versions_manage(
    rule_id: uuid.UUID,
    current_user: dict = Depends(deps.require_university_rep),
):
    """История версий доступна представителю и для непроверенного правила."""
    try:
        rule = await _get_rule_or_404(rule_id)
        await _ensure_manage(rule, current_user)
        return {'versions': await database.benefits.list_versions(rule_id)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.get('/{rule_id}/versions')
async def list_versions_rule(rule_id: uuid.UUID):
    return await list_versions(rule_id)


@benefits_page.post('/{rule_id}/rollback')
async def rollback_benefit(
    rule_id: uuid.UUID,
    body: RollbackRequest,
    current_user: dict = Depends(deps.require_university_rep),
):
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    try:
        updated = await database.benefits.rollback(
            rule_id,
            body.version,
            user_id=current_user['id'],
            expected_version=body.expected_version,
        )
    except database.benefits.InvalidReference as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except database.benefits.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    if not updated:
        raise HTTPException(status_code=404, detail='Version not found')
    await database.audit.log_action(
        'benefit_rule', rule_id, 'rollback',
        user_id=current_user['id'], after=updated,
    )
    return updated


@benefit_rules_page.post('/{rule_id}/rollback')
async def rollback_benefit_rule(
    rule_id: uuid.UUID,
    body: RollbackRequest,
    current_user: dict = Depends(deps.require_university_rep),
):
    return await rollback_benefit(rule_id, body, current_user)


@benefits_page.get('/{rule_id}/versions/{version_number}')
async def get_version(rule_id: uuid.UUID, version_number: int):
    await _get_rule_or_404(rule_id, public_only=True)
    versions = await database.benefits.list_versions(rule_id)
    for version in versions:
        if version['version_number'] == version_number:
            return version
    raise HTTPException(status_code=404, detail='Version not found')


@benefits_page.get('/{rule_id}/status-history')
async def status_history(rule_id: uuid.UUID):
    try:
        await _get_rule_or_404(rule_id, public_only=True)
        history = await database.benefits.list_status_history(rule_id)
        return {'history': history}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.get('/{rule_id}/status-history/manage')
async def status_history_manage(
    rule_id: uuid.UUID,
    current_user: dict = Depends(deps.require_university_rep),
):
    try:
        rule = await _get_rule_or_404(rule_id)
        await _ensure_manage(rule, current_user)
        return {'history': await database.benefits.list_status_history(rule_id)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


# -------------------------------------------------------------------- admin


@admin_benefits_page.get('')
async def admin_list_benefits(
    university_id: uuid.UUID | None = None,
    olympiad_id: uuid.UUID | None = None,
    verification_status: str | None = None,
    season_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    level: str | None = Query(default=None, pattern='^[123]$'),
    needs_review: bool | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    try:
        rules, total = await database.benefits.list_rules(
            university_id=university_id,
            olympiad_id=olympiad_id,
            verification_status=verification_status,
            season_id=season_id,
            profile_id=profile_id,
            level=level,
            needs_review=needs_review,
            search=search,
            public_only=False,
            limit=limit,
            offset=offset,
        )
        return {
            'rules': rules,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@admin_benefits_page.get('/{rule_id}')
async def admin_get_benefit(
    rule_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    return await _get_handler(rule_id, public_only=False)


@admin_benefits_page.get('/{rule_id}/versions')
async def admin_versions(
    rule_id: uuid.UUID,
    current_user: deps.AdminUser = None,
):
    try:
        await _get_rule_or_404(rule_id, public_only=False)
        return {'versions': await database.benefits.list_versions(rule_id)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
