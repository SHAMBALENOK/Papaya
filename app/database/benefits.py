import uuid as uuid_mod
import json
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.models.benefits import (
    BenefitRule,
    BenefitRuleProgram,
    BenefitRuleVersion,
    BenefitStatusHistory,
)

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))

_BENEFIT_TYPE_ALIASES = {
    'бви': 'BVI',
    'без вступительных': 'BVI',
    '100 егэ': 'EGE_100',
    '100 баллов егэ': 'EGE_100',
    'ege_100': 'EGE_100',
    '100 дви': 'DVI_100',
    '100 баллов дви': 'DVI_100',
    'dvi_100': 'DVI_100',
    'другие': 'OTHER',
    'другие преимущества': 'OTHER',
    'other': 'OTHER',
}

_STATUS_ALIASES = {
    'непроверено': 'unverified',
    'не проверено': 'unverified',
    'проверено': 'verified',
    'отклонено': 'rejected',
}

def normalize_status(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in _STATUS_ALIASES:
        return _STATUS_ALIASES[v]
    if v in ('unverified', 'verified', 'rejected'):
        return v
    return str(value).strip()

def normalize_benefit_type(value):
    if value is None:
        return None
    v = str(value).strip()
    key = v.lower()
    if key in _BENEFIT_TYPE_ALIASES:
        return _BENEFIT_TYPE_ALIASES[key]
    upper = v.upper()
    if upper in ('BVI', 'EGE_100', 'DVI_100', 'OTHER'):
        return upper
    return v

def _iso(v):
    return v.isoformat() if v else None

def rule_to_dict(r, program_ids=None):
    return {
        'id': str(r.id),
        'university_id': str(r.university_id),
        'olympiad_id': str(r.olympiad_id),
        'season_id': str(r.season_id) if r.season_id else None,
        'profile_id': str(r.profile_id) if r.profile_id else None,
        'benefit_type': r.benefit_type,
        'required_result': r.required_result,
        'subject': r.subject,
        'additional_requirements': r.additional_requirements,
        'program_ids': program_ids if program_ids is not None else [str(p.id) for p in getattr(r, 'programs', [])],
        'doc_id': str(r.doc_id) if r.doc_id else None,
        'source_url': r.source_url,
        'verification_status': r.verification_status,
        'rejection_reason': r.rejection_reason,
        'is_published': r.is_published,
        'version': r.version,
        'created_by': str(r.created_by) if r.created_by else None,
        'updated_by': str(r.updated_by) if r.updated_by else None,
        'createdAt': _iso(r.createdAt),
        'updatedAt': _iso(r.updatedAt),
    }

async def _program_ids(session, rule_id):
    result = await session.execute(
        select(BenefitRuleProgram.program_id).where(BenefitRuleProgram.rule_id == _as_uuid(rule_id))
    )
    return [str(x) for x in result.scalars().all()]

async def get_rule(rule_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BenefitRule).where(BenefitRule.id == _as_uuid(rule_id)))
        r = result.scalar_one_or_none()
        if not r:
            return None
        pids = await _program_ids(session, rule_id)
        return rule_to_dict(r, pids)

async def list_rules(*, university_id=None, olympiad_id=None, benefit_type=None, subject=None, program_id=None, verification_status=None):
    async with AsyncSessionLocal() as session:
        stmt = select(BenefitRule)
        if university_id:
            stmt = stmt.where(BenefitRule.university_id == _as_uuid(university_id))
        if olympiad_id:
            stmt = stmt.where(BenefitRule.olympiad_id == _as_uuid(olympiad_id))
        if benefit_type:
            benefit_type = normalize_benefit_type(benefit_type)
            stmt = stmt.where(BenefitRule.benefit_type == benefit_type)
        if subject:
            stmt = stmt.where(BenefitRule.subject == subject)
        if verification_status:
            verification_status = normalize_status(verification_status)
            stmt = stmt.where(BenefitRule.verification_status == verification_status)
        result = await session.execute(stmt)
        rules = result.scalars().all()
        out = []
        for r in rules:
            pids = await _program_ids(session, r.id)
            if program_id and program_id not in pids:
                continue
            out.append(rule_to_dict(r, pids))
        return out

async def create_rule(data: dict, program_ids=None, user_id=None):
    async with AsyncSessionLocal() as session:
        r = BenefitRule(
            university_id=_as_uuid(data['university_id']),
            olympiad_id=_as_uuid(data['olympiad_id']),
            season_id=_as_uuid(data['season_id']) if data.get('season_id') else None,
            profile_id=_as_uuid(data['profile_id']) if data.get('profile_id') else None,
            benefit_type=normalize_benefit_type(data.get('benefit_type', 'BVI')),
            required_result=data.get('required_result'),
            subject=data.get('subject'),
            additional_requirements=data.get('additional_requirements'),
            doc_id=_as_uuid(data['doc_id']) if data.get('doc_id') else None,
            source_url=data.get('source_url'),
            verification_status=normalize_status(data.get('verification_status', 'unverified')),
            is_published=data.get('is_published', True),
            created_by=_as_uuid(user_id) if user_id else None,
            updated_by=_as_uuid(user_id) if user_id else None,
        )
        session.add(r)
        await session.flush()
        for pid in (program_ids or []):
            session.add(BenefitRuleProgram(rule_id=r.id, program_id=_as_uuid(pid)))
        # version 1 snapshot
        await session.flush()
        await _create_version(session, r, changed_by=user_id, changed_fields=['*'], reason='created')
        await session.commit()
        await session.refresh(r)
        pids = await _program_ids(session, r.id)
        return rule_to_dict(r, pids)

async def _snapshot(r, program_ids):
    return {
        'id': str(r.id),
        'university_id': str(r.university_id),
        'olympiad_id': str(r.olympiad_id),
        'season_id': str(r.season_id) if r.season_id else None,
        'profile_id': str(r.profile_id) if r.profile_id else None,
        'benefit_type': r.benefit_type,
        'required_result': r.required_result,
        'subject': r.subject,
        'additional_requirements': r.additional_requirements,
        'program_ids': program_ids,
        'doc_id': str(r.doc_id) if r.doc_id else None,
        'source_url': r.source_url,
        'verification_status': r.verification_status,
        'is_published': r.is_published,
        'version': r.version,
    }

async def _create_version(session, r, changed_by=None, changed_fields=None, reason=None):
    pids = [str(x.program_id) for x in (await session.execute(
        select(BenefitRuleProgram).where(BenefitRuleProgram.rule_id == r.id)
    )).scalars().all()]
    snap = await _snapshot(r, pids)
    v = BenefitRuleVersion(
        rule_id=r.id,
        version_number=r.version,
        snapshot=snap,
        changed_fields=changed_fields or [],
        change_reason=reason,
        verification_status=r.verification_status,
        doc_id=r.doc_id,
        source_url=r.source_url,
        changed_by=_as_uuid(changed_by) if changed_by else None,
    )
    session.add(v)

async def update_rule(rule_id, data: dict, program_ids=None, user_id=None, reason=None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BenefitRule).where(BenefitRule.id == _as_uuid(rule_id)))
        r = result.scalar_one_or_none()
        if not r:
            return None
        changed = []
        for k in ('season_id', 'profile_id', 'benefit_type', 'required_result', 'subject',
                  'additional_requirements', 'doc_id', 'source_url', 'is_published'):
            if k in data and data[k] is not None:
                new_val = data[k]
                if k in ('season_id', 'profile_id', 'doc_id') and new_val:
                    new_val = _as_uuid(new_val)
                if getattr(r, k) != new_val:
                    changed.append(k)
                setattr(r, k, new_val)
        if 'verification_status' in data and data['verification_status'] is not None:
            new_status = normalize_status(data['verification_status'])
            if r.verification_status != new_status:
                # status history
                session.add(BenefitStatusHistory(
                    rule_id=r.id,
                    from_status=r.verification_status,
                    to_status=new_status,
                    changed_by=_as_uuid(user_id) if user_id else None,
                    reason=reason,
                ))
                changed.append('verification_status')
                r.verification_status = new_status
        # programs
        if program_ids is not None:
            # replace
            await session.execute(
                delete(BenefitRuleProgram).where(BenefitRuleProgram.rule_id == r.id)
            )
            for pid in program_ids:
                session.add(BenefitRuleProgram(rule_id=r.id, program_id=_as_uuid(pid)))
            changed.append('program_ids')
        r.version = (r.version or 1) + 1
        r.updated_by = _as_uuid(user_id) if user_id else r.updated_by
        await session.flush()
        await _create_version(session, r, changed_by=user_id, changed_fields=changed, reason=reason)
        await session.commit()
        await session.refresh(r)
        pids = await _program_ids(session, r.id)
        return rule_to_dict(r, pids)

async def set_status(rule_id, new_status, user_id=None, reason=None):
    return await update_rule(rule_id, {'verification_status': new_status}, user_id=user_id, reason=reason)

async def list_versions(rule_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitRuleVersion).where(BenefitRuleVersion.rule_id == _as_uuid(rule_id)).order_by(BenefitRuleVersion.version_number)
        )
        versions = result.scalars().all()
        return [
            {
                'id': str(v.id),
                'rule_id': str(v.rule_id),
                'version_number': v.version_number,
                'snapshot': v.snapshot,
                'changed_fields': v.changed_fields,
                'change_reason': v.change_reason,
                'verification_status': v.verification_status,
                'doc_id': str(v.doc_id) if v.doc_id else None,
                'source_url': v.source_url,
                'changed_by': str(v.changed_by) if v.changed_by else None,
                'changed_at': _iso(v.changed_at),
            }
            for v in versions
        ]

async def rollback(rule_id, version_number, user_id=None):
    async with AsyncSessionLocal() as session:
        vresult = await session.execute(
            select(BenefitRuleVersion).where(
                BenefitRuleVersion.rule_id == _as_uuid(rule_id),
                BenefitRuleVersion.version_number == version_number,
            )
        )
        v = vresult.scalar_one_or_none()
        if not v:
            return None
        rresult = await session.execute(select(BenefitRule).where(BenefitRule.id == _as_uuid(rule_id)))
        r = rresult.scalar_one_or_none()
        if not r:
            return None
        snap = v.snapshot or {}
        # apply snapshot fields
        r.season_id = _as_uuid(snap['season_id']) if snap.get('season_id') else None
        r.profile_id = _as_uuid(snap['profile_id']) if snap.get('profile_id') else None
        r.benefit_type = snap.get('benefit_type', r.benefit_type)
        r.required_result = snap.get('required_result')
        r.subject = snap.get('subject')
        r.additional_requirements = snap.get('additional_requirements')
        r.doc_id = _as_uuid(snap['doc_id']) if snap.get('doc_id') else None
        r.source_url = snap.get('source_url')
        r.is_published = snap.get('is_published', True)
        # verification status not auto-verified
        new_status = snap.get('verification_status', 'unverified')
        if new_status == 'verified':
            new_status = 'unverified'
        r.verification_status = new_status
        r.version = (r.version or 1) + 1
        r.updated_by = _as_uuid(user_id) if user_id else r.updated_by
        # programs replace
        await session.execute(
            delete(BenefitRuleProgram).where(BenefitRuleProgram.rule_id == r.id)
        )
        for pid in snap.get('program_ids') or []:
            session.add(BenefitRuleProgram(rule_id=r.id, program_id=_as_uuid(pid)))
        await session.flush()
        await _create_version(session, r, changed_by=user_id, changed_fields=['rollback'], reason=f'rollback to v{version_number}')
        await session.commit()
        await session.refresh(r)
        pids = await _program_ids(session, r.id)
        return rule_to_dict(r, pids)

async def list_status_history(rule_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitStatusHistory).where(BenefitStatusHistory.rule_id == _as_uuid(rule_id)).order_by(BenefitStatusHistory.changed_at)
        )
        return [
            {
                'id': str(h.id),
                'rule_id': str(h.rule_id),
                'from_status': h.from_status,
                'to_status': h.to_status,
                'changed_by': str(h.changed_by) if h.changed_by else None,
                'changed_at': _iso(h.changed_at),
                'reason': h.reason,
            }
            for h in result.scalars().all()
        ]