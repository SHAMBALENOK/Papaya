"""API правил льгот.

Публичная часть каталога отдаёт только проверенные опубликованные правила.
Представитель может создавать и править правила своего университета, но не
может подтверждать их: ``verified`` выставляется исключительно администратором
через ``/verify``. Любая содержательная правка проверенного правила снимает
проверку.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app import database
from app.core import deps
from app.schemas.urls import ExternalUrl

benefits_page = APIRouter(prefix='/benefits', tags=['benefits'])
benefit_rules_page = APIRouter(prefix='/benefit-rules', tags=['benefits'])
university_benefits_page = APIRouter(tags=['benefits'])
olympiad_benefits_page = APIRouter(tags=['benefits'])
admin_benefits_page = APIRouter(prefix='/admin/benefits', tags=['benefits'])

logger = logging.getLogger('papaya.benefits')

BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')
RESULT_TYPES = ('WINNER', 'PRIZE', 'SCORE', 'OTHER')
VERIFICATION_STATUSES = ('unverified', 'verified', 'rejected')
MAX_PAGE_SIZE = 200


def _check_benefit_type(v):
    if v is None:
        return v
    normalized = database.benefits.normalize_benefit_type(v)
    if normalized not in BENEFIT_TYPES:
        raise ValueError('benefit_type must be one of ' + ', '.join(BENEFIT_TYPES))
    return normalized


def _check_result_type(v):
    if v is None:
        return v
    if v not in RESULT_TYPES:
        raise ValueError('required_result_type must be one of ' + ', '.join(RESULT_TYPES))
    return v


class BenefitCreate(BaseModel):
    olympiad_id: uuid.UUID
    season_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    benefit_type: str = 'BVI'
    required_result: str | None = None
    required_result_type: str | None = None
    required_result_value: str | None = None
    subject: str | None = None
    additional_requirements: str | None = None
    program_ids: List[uuid.UUID] | None = None
    doc_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    source_url: ExternalUrl = None
    # Поле принимается для совместимости, но игнорируется: подтверждение —
    # отдельное действие администратора.
    verification_status: str | None = None
    is_published: bool | None = None

    _benefit_type = field_validator('benefit_type')(_check_benefit_type)
    _required_result_type = field_validator('required_result_type')(_check_result_type)

    @field_validator('verification_status')
    @classmethod
    def _check_status(cls, v):
        if v is not None and v not in VERIFICATION_STATUSES:
            raise ValueError(
                'verification_status must be one of '
                + ', '.join(VERIFICATION_STATUSES)
            )
        return v


class BenefitUpdate(BaseModel):
    version: int | None = Field(default=None, ge=1)
    season_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    benefit_type: str | None = None
    required_result: str | None = None
    required_result_type: str | None = None
    required_result_value: str | None = None
    subject: str | None = None
    additional_requirements: str | None = None
    program_ids: List[uuid.UUID] | None = None
    doc_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    source_url: ExternalUrl = None
    verification_status: str | None = None
    is_published: bool | None = None
    change_reason: str | None = None

    _benefit_type = field_validator('benefit_type')(_check_benefit_type)
    _required_result_type = field_validator('required_result_type')(_check_result_type)

    @field_validator('verification_status')
    @classmethod
    def _check_status(cls, v):
        if v is not None and v not in VERIFICATION_STATUSES:
            raise ValueError(
                'verification_status must be one of '
                + ', '.join(VERIFICATION_STATUSES)
            )
        return v


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


class RollbackRequest(BaseModel):
    version: int = Field(ge=1)


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
    """Проверить, что сезон/профиль/программы/документ принадлежат вузу.

    Внешние ключи в БД не выражают эти инварианты: ``season_id`` может
    относиться к другой олимпиаде, а ``program_id`` — к другому университету.
    """
    olympiad_id = data.get('olympiad_id') or (existing or {}).get('olympiad_id')
    season_id = data.get('season_id', (existing or {}).get('season_id'))
    profile_id = data.get('profile_id', (existing or {}).get('profile_id'))

    if olympiad_id:
        olympiad = await database.olympiads.get_olympiad(olympiad_id)
        if not olympiad:
            raise HTTPException(status_code=400, detail='Olympiad not found')
        # Архивированная олимпиада не принимает новых правил, но уже
        # существующее правило остаётся редактируемым: история и источник
        # связи важнее актуальности каталога.
        if existing is None and olympiad.get('status') == 'ARCHIVED':
            raise HTTPException(
                status_code=400,
                detail='Olympiad is archived and accepts no new benefit rules',
            )

    if season_id:
        season = await database.seasons.get_season(season_id)
        if not season:
            raise HTTPException(status_code=400, detail='Season not found')
        if olympiad_id and str(season.get('olympiad_id')) != str(olympiad_id):
            raise HTTPException(
                status_code=400,
                detail='Season does not belong to the selected olympiad',
            )

    if profile_id:
        if not season_id:
            raise HTTPException(
                status_code=400,
                detail='Profile requires a season',
            )
        profile = await database.seasons.get_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=400, detail='Profile not found')
        if str(profile.get('season_id')) != str(season_id):
            raise HTTPException(
                status_code=400,
                detail='Profile does not belong to the selected season',
            )

    program_ids = data.get('program_ids')
    if program_ids is not None:
        for program_id in program_ids:
            program = await database.programs.get_program(program_id)
            if not program:
                raise HTTPException(
                    status_code=400, detail=f'Program {program_id} not found'
                )
            if str(program.get('university_id')) != str(university_id):
                raise HTTPException(
                    status_code=400,
                    detail='Program does not belong to the university',
                )

    doc_id = data.get('doc_id')
    if doc_id:
        doc = await database.docs.get_doc(doc_id)
        if not doc:
            raise HTTPException(status_code=400, detail='Document not found')
        doc_university = doc.get('university_id')
        is_admin = current_user.get('role') == deps.ROLE_ADMIN
        if doc_university and str(doc_university) != str(university_id):
            raise HTTPException(
                status_code=400,
                detail='Document belongs to another university',
            )
        if not is_admin and doc_university is None:
            # Общий документ (например, перечень РСОШ) может приложить
            # администратор; представитель прикладывает только свой приказ.
            raise HTTPException(
                status_code=400,
                detail='Representative can attach only a document of own university',
            )

    source_id = data.get('source_id')
    if source_id:
        source = await database.sources.get_source(source_id)
        if not source:
            raise HTTPException(status_code=400, detail='Source not found')
        source_university = source.get('university_id')
        if source_university and str(source_university) != str(university_id):
            raise HTTPException(
                status_code=400,
                detail='Source belongs to another university',
            )


def _page_params(limit, offset):
    if limit is None:
        limit = 50
    return min(max(1, int(limit)), MAX_PAGE_SIZE), max(0, int(offset or 0))


async def _list_handler(
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    subject=None,
    program_id=None,
    verification_status=None,
    search=None,
    season_id=None,
    limit=50,
    offset=0,
):
    limit, offset = _page_params(limit, offset)
    rules, total = await database.benefits.list_rules(
        university_id=university_id,
        olympiad_id=olympiad_id,
        benefit_type=benefit_type,
        subject=subject,
        program_id=program_id,
        verification_status=verification_status,
        search=search,
        season_id=season_id,
        public_only=True,
        limit=limit,
        offset=offset,
    )
    return {
        'rules': rules,
        'total': total,
        'limit': limit,
        'offset': offset,
    }


# ---------------------------------------------------------------- public list


@benefits_page.get('')
async def list_benefits(
    university_id: uuid.UUID | None = Query(default=None),
    olympiad_id: uuid.UUID | None = Query(default=None),
    benefit_type: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    program_id: uuid.UUID | None = Query(default=None),
    season_id: uuid.UUID | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        return await _list_handler(
            university_id=university_id,
            olympiad_id=olympiad_id,
            benefit_type=benefit_type,
            subject=subject,
            program_id=program_id,
            season_id=season_id,
            verification_status=verification_status,
            search=search,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.get('')
async def list_benefit_rules(
    university_id: uuid.UUID | None = Query(default=None),
    olympiad_id: uuid.UUID | None = Query(default=None),
    benefit_type: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    program_id: uuid.UUID | None = Query(default=None),
    season_id: uuid.UUID | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await list_benefits(
        university_id=university_id,
        olympiad_id=olympiad_id,
        benefit_type=benefit_type,
        subject=subject,
        program_id=program_id,
        season_id=season_id,
        verification_status=verification_status,
        search=search,
        limit=limit,
        offset=offset,
    )


@university_benefits_page.get('/universities/{university_id}/benefits')
async def list_university_benefits(
    university_id: uuid.UUID,
    benefit_type: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    program_id: uuid.UUID | None = Query(default=None),
    season_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        rules, total = await database.benefits.list_rules(
            university_id=str(university_id),
            benefit_type=benefit_type,
            subject=subject,
            program_id=program_id,
            season_id=season_id,
            public_only=True,
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


@university_benefits_page.get('/universities/{university_id}/benefit-rules')
async def list_university_benefit_rules(
    university_id: uuid.UUID,
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
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
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(deps.require_manage_university),
):
    """Рабочий список правил своего университета, включая черновики.

    Публичный список отдаёт только ``verified + is_published``. Представителю
    нужны и непроверенные правила: без этого он не смог бы продолжить работу
    над черновиком или увидеть причину отказа.
    """
    try:
        rules, total = await database.benefits.list_rules(
            university_id=str(university_id),
            verification_status=verification_status,
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


@benefits_page.get('/olympiad/{olympiad_id}')
async def list_olympiad_benefits(
    olympiad_id: uuid.UUID,
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        return await _list_handler(
            olympiad_id=olympiad_id, limit=limit, offset=offset
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiad_benefits_page.get('/olympiads/{olympiad_id}/benefits')
async def list_olympiad_benefits_alias(
    olympiad_id: uuid.UUID,
    limit: int | None = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await list_olympiad_benefits(olympiad_id, limit, offset)


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
    if isinstance(data.get('source_url'), str):
        data['source_url'] = data['source_url'].strip()
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        await _validate_refs(university_id, data, current_user)
        rule = await database.benefits.create_rule(
            data,
            program_ids=data.pop('program_ids', None),
            user_id=current_user['id'],
        )
        await database.audit.log_action(
            'benefit_rule', rule['id'], 'create',
            user_id=current_user['id'], after=rule,
        )
        return rule
    except HTTPException:
        raise
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
    program_ids = data.pop('program_ids', None)
    data['program_ids'] = program_ids
    try:
        await _validate_refs(
            rule['university_id'], data, current_user, existing=rule
        )
        updated = await database.benefits.update_rule(
            rule_id,
            {k: v for k, v in data.items() if k != 'program_ids'},
            program_ids=program_ids,
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
    if body.status == 'verified' and current_user.get('role') != deps.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail='Only admin can verify')
    if body.status == 'verified':
        if not rule.get('doc_id') or not rule.get('source_url'):
            raise HTTPException(
                status_code=400,
                detail='Document and source URL required for verification',
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
    if not rule.get('doc_id') or not rule.get('source_url'):
        raise HTTPException(
            status_code=400,
            detail='Document and source URL required for verification',
        )
    try:
        updated = await database.benefits.set_status(
            rule_id, 'verified',
            user_id=current_user['id'], reason='verified by admin',
            expected_version=rule['version'],
        )
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
    body: StatusChange | None = None,
    current_user: dict = Depends(deps.require_admin),
):
    rule = await _get_rule_or_404(rule_id)
    reason = body.reason if body else None
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
    updated = await database.benefits.rollback(
        rule_id, body.version, user_id=current_user['id']
    )
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
    university_id: uuid.UUID | None = Query(default=None),
    olympiad_id: uuid.UUID | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: deps.AdminUser = None,
):
    try:
        rules, total = await database.benefits.list_rules(
            university_id=university_id,
            olympiad_id=olympiad_id,
            verification_status=verification_status,
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
