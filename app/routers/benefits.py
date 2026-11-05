import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app import database
from app.core import deps

benefits_page = APIRouter(prefix='/benefits', tags=['benefits'])
benefit_rules_page = APIRouter(prefix='/benefit-rules', tags=['benefits'])
university_benefits_page = APIRouter(tags=['benefits'])
olympiad_benefits_page = APIRouter(tags=['benefits'])

logger = logging.getLogger('papaya.benefits')


class BenefitCreate(BaseModel):
    olympiad_id: str
    season_id: str | None = None
    profile_id: str | None = None
    benefit_type: str = 'BVI'
    required_result: str | None = None
    subject: str | None = None
    additional_requirements: str | None = None
    program_ids: list[str] | None = None
    doc_id: str | None = None
    source_url: str | None = None
    verification_status: str | None = None
    is_published: bool | None = None


class BenefitUpdate(BaseModel):
    version: int | None = None
    season_id: str | None = None
    profile_id: str | None = None
    benefit_type: str | None = None
    required_result: str | None = None
    subject: str | None = None
    additional_requirements: str | None = None
    program_ids: list[str] | None = None
    doc_id: str | None = None
    source_url: str | None = None
    verification_status: str | None = None
    is_published: bool | None = None
    change_reason: str | None = None


class StatusChange(BaseModel):
    status: str
    reason: str | None = None


class RollbackRequest(BaseModel):
    version: int


async def _ensure_manage(rule, current_user):
    if not deps.can_manage_university(current_user, rule['university_id']):
        raise HTTPException(status_code=403, detail='You can only manage your own university')


async def _get_rule_or_404(rule_id):
    rule = await database.benefits.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail='Benefit rule not found')
    return rule


# List/filter
async def _list_handler(university_id=None, olympiad_id=None, benefit_type=None, subject=None, program_id=None, verification_status=None):
    try:
        rules = await database.benefits.list_rules(
            university_id=university_id,
            olympiad_id=olympiad_id,
            benefit_type=benefit_type,
            subject=subject,
            program_id=program_id,
            verification_status=verification_status,
        )
        return {'rules': rules}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.get('')
async def list_benefits(
    university_id: str | None = Query(default=None),
    olympiad_id: str | None = Query(default=None),
    benefit_type: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    program_id: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
):
    return await _list_handler(university_id, olympiad_id, benefit_type, subject, program_id, verification_status)


@benefit_rules_page.get('')
async def list_benefit_rules(
    university_id: str | None = Query(default=None),
    olympiad_id: str | None = Query(default=None),
    benefit_type: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    program_id: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
):
    return await _list_handler(university_id, olympiad_id, benefit_type, subject, program_id, verification_status)


@university_benefits_page.get('/universities/{university_id}/benefits')
async def list_university_benefits(university_id: uuid.UUID):
    try:
        rules = await database.benefits.list_rules(university_id=str(university_id))
        return {'rules': rules}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_benefits_page.get('/universities/{university_id}/benefit-rules')
async def list_university_benefit_rules(university_id: uuid.UUID):
    return await list_university_benefits(university_id)


@benefits_page.get('/olympiad/{olympiad_id}')
async def list_olympiad_benefits(olympiad_id: uuid.UUID):
    try:
        rules = await database.benefits.list_rules(olympiad_id=str(olympiad_id))
        return {'rules': rules}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@olympiad_benefits_page.get('/olympiads/{olympiad_id}/benefits')
async def list_olympiad_benefits2(olympiad_id: uuid.UUID):
    return await list_olympiad_benefits(olympiad_id)


# Create under university
async def _create_handler(university_id, body, current_user):
    if not deps.can_manage_university(current_user, university_id):
        raise HTTPException(status_code=403, detail='You can only manage your own university')
    try:
        data = body.model_dump()
        data['university_id'] = str(university_id)
        if data.get('verification_status') == 'verified':
            if not data.get('doc_id') or not data.get('source_url'):
                raise HTTPException(status_code=400, detail='Document and source URL required for verification')
        rule = await database.benefits.create_rule(data, program_ids=data.pop('program_ids', None), user_id=current_user['id'])
        await database.audit.log_action('benefit_rule', rule['id'], 'create', user_id=current_user['id'], after=rule)
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_benefits_page.post('/universities/{university_id}/benefits')
async def create_university_benefit(university_id: uuid.UUID, body: BenefitCreate, current_user: dict = Depends(deps.require_university_rep)):
    return await _create_handler(university_id, body, current_user)


@university_benefits_page.post('/universities/{university_id}/benefit-rules')
async def create_university_benefit_rule(university_id: uuid.UUID, body: BenefitCreate, current_user: dict = Depends(deps.require_university_rep)):
    return await _create_handler(university_id, body, current_user)


# Detail
async def _get_handler(rule_id):
    try:
        rule = await _get_rule_or_404(rule_id)
        return rule
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


# Update
async def _update_handler(rule_id, body, current_user):
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    expected = getattr(body, 'version', None)
    if expected is not None and int(expected) != int(rule.get('version', 0)):
        raise HTTPException(status_code=409, detail='Version conflict')
    try:
        data = body.model_dump(exclude_unset=True)
        data.pop('version', None)
        reason = data.pop('change_reason', None)
        program_ids = data.pop('program_ids', None)
        if data.get('verification_status') == 'verified':
            rule = await database.benefits.get_rule(rule_id)
            doc_id = data.get('doc_id', rule.get('doc_id'))
            source_url = data.get('source_url', rule.get('source_url'))
            if not doc_id or not source_url:
                raise HTTPException(status_code=400, detail='Document and source URL required for verification')
        updated = await database.benefits.update_rule(rule_id, data, program_ids=program_ids, user_id=current_user['id'], reason=reason)
        if not updated:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        await database.audit.log_action('benefit_rule', rule_id, 'update', user_id=current_user['id'], before=rule, after=updated)
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefits_page.put('/{rule_id}')
async def update_benefit(rule_id: uuid.UUID, body: BenefitUpdate, current_user: dict = Depends(deps.require_university_rep)):
    return await _update_handler(rule_id, body, current_user)


@benefit_rules_page.put('/{rule_id}')
async def update_benefit_rule(rule_id: uuid.UUID, body: BenefitUpdate, current_user: dict = Depends(deps.require_university_rep)):
    return await _update_handler(rule_id, body, current_user)


@benefits_page.patch('/{rule_id}')
async def patch_benefit(rule_id: uuid.UUID, body: BenefitUpdate, current_user: dict = Depends(deps.require_university_rep)):
    return await _update_handler(rule_id, body, current_user)


@benefit_rules_page.patch('/{rule_id}')
async def patch_benefit_rule(rule_id: uuid.UUID, body: BenefitUpdate, current_user: dict = Depends(deps.require_university_rep)):
    return await _update_handler(rule_id, body, current_user)


# Delete? no physical delete; archive via status rejected maybe. Keep no delete.

# Status
@benefits_page.post('/{rule_id}/status')
async def change_status(rule_id: uuid.UUID, body: StatusChange, current_user: dict = Depends(deps.require_university_rep)):
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    # admin can verify; rep can only set unverified? Allow status changes but verification requires admin for verified
    new_status = body.status
    if new_status == 'verified' and current_user.get('role') != 'ADMIN':
        raise HTTPException(status_code=403, detail='Only admin can verify')
    if new_status == 'verified':
        rule = await database.benefits.get_rule(rule_id)
        if not rule.get('doc_id') or not rule.get('source_url'):
            raise HTTPException(status_code=400, detail='Document and source URL required for verification')
    try:
        updated = await database.benefits.set_status(rule_id, new_status, user_id=current_user['id'], reason=body.reason)
        await database.audit.log_action('benefit_rule', rule_id, 'status_change', user_id=current_user['id'], after=updated)
        return updated
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.post('/{rule_id}/status')
async def change_status_rule(rule_id: uuid.UUID, body: StatusChange, current_user: dict = Depends(deps.require_university_rep)):
    return await change_status(rule_id, body, current_user)


# Admin verify/reject endpoints
@benefits_page.post('/{rule_id}/verify')
async def verify_benefit(rule_id: uuid.UUID, current_user: dict = Depends(deps.require_admin)):
    rule = await _get_rule_or_404(rule_id)
    # require doc and source_url for verified
    if not rule.get('doc_id') or not rule.get('source_url'):
        raise HTTPException(status_code=400, detail='Document and source URL required for verification')
    updated = await database.benefits.set_status(rule_id, 'verified', user_id=current_user['id'], reason='verified by admin')
    return updated


@benefits_page.post('/{rule_id}/reject')
async def reject_benefit(rule_id: uuid.UUID, body: StatusChange | None = None, current_user: dict = Depends(deps.require_admin)):
    reason = body.reason if body else None
    updated = await database.benefits.set_status(rule_id, 'rejected', user_id=current_user['id'], reason=reason)
    return updated


# Versions
@benefits_page.get('/{rule_id}/versions')
async def list_versions(rule_id: uuid.UUID):
    try:
        versions = await database.benefits.list_versions(rule_id)
        return {'versions': versions}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.get('/{rule_id}/versions')
async def list_versions_rule(rule_id: uuid.UUID):
    return await list_versions(rule_id)


@benefits_page.post('/{rule_id}/rollback')
async def rollback_benefit(rule_id: uuid.UUID, body: RollbackRequest, current_user: dict = Depends(deps.require_university_rep)):
    rule = await _get_rule_or_404(rule_id)
    await _ensure_manage(rule, current_user)
    # admin can rollback any; rep own already ensured
    updated = await database.benefits.rollback(rule_id, body.version, user_id=current_user['id'])
    if not updated:
        raise HTTPException(status_code=404, detail='Version not found')
    await database.audit.log_action('benefit_rule', rule_id, 'rollback', user_id=current_user['id'], after=updated)
    return updated


@benefit_rules_page.post('/{rule_id}/rollback')
async def rollback_benefit_rule(rule_id: uuid.UUID, body: RollbackRequest, current_user: dict = Depends(deps.require_university_rep)):
    return await rollback_benefit(rule_id, body, current_user)


@benefits_page.get('/{rule_id}/versions/{version_number}')
async def get_version(rule_id: uuid.UUID, version_number: int):
    versions = await database.benefits.list_versions(rule_id)
    for v in versions:
        if v['version_number'] == version_number:
            return v
    raise HTTPException(status_code=404, detail='Version not found')


@benefits_page.get('/{rule_id}/status-history')
async def status_history(rule_id: uuid.UUID):
    try:
        history = await database.benefits.list_status_history(rule_id)
        return {'history': history}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')