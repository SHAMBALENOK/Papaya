"""Слой доступа к правилам льгот.

Публичные выборки отдают только проверенные и опубликованные правила:
черновик и отклонённая запись — рабочий материал модерации, а не факт
каталога. Фильтрация и пагинация выполняются в SQL, а не в Python: иначе
`program_id` тянул бы весь каталог, а страница не могла бы ответить `total`.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.models.benefits import (
    BenefitRule,
    BenefitRuleProgram,
    BenefitRuleVersion,
    BenefitStatusHistory,
)
from app.models.programs import UniversityProgram


class VersionConflict(Exception):
    """Версия правила изменилась между чтением и записью."""


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

#: Поля, изменение которых делает проверенную льготу снова непроверенной.
_CONTENT_FIELDS = frozenset({
    'season_id', 'profile_id', 'benefit_type', 'required_result',
    'required_result_type', 'required_result_value', 'subject',
    'additional_requirements', 'doc_id', 'source_id', 'source_url',
    # Привязка к программам — тоже содержание правила: иначе проверенную
    # льготу можно было бы переназначить на другие направления, оставшись
    # «проверенной».
    'program_ids',
})


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


def _program_ids_from_rule(r):
    return [str(p.id) for p in (getattr(r, 'programs', None) or [])]


def rule_to_dict(r, program_ids=None):
    return {
        'id': str(r.id),
        'university_id': str(r.university_id),
        'olympiad_id': str(r.olympiad_id),
        'season_id': str(r.season_id) if r.season_id else None,
        'profile_id': str(r.profile_id) if r.profile_id else None,
        'benefit_type': r.benefit_type,
        'required_result': r.required_result,
        'required_result_type': getattr(r, 'required_result_type', None),
        'required_result_value': getattr(r, 'required_result_value', None),
        'subject': r.subject,
        'additional_requirements': r.additional_requirements,
        'program_ids': (
            program_ids
            if program_ids is not None
            else _program_ids_from_rule(r)
        ),
        'doc_id': str(r.doc_id) if r.doc_id else None,
        'source_id': str(r.source_id) if getattr(r, 'source_id', None) else None,
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
        select(BenefitRuleProgram.program_id).where(
            BenefitRuleProgram.rule_id == _as_uuid(rule_id)
        )
    )
    return [str(x) for x in result.scalars().all()]


def _rule_query():
    # selectinload обязателен: без него обращение к ``rule.programs`` в
    # async-сессии падает с MissingGreenlet.
    return select(BenefitRule).options(selectinload(BenefitRule.programs))


def _apply_filters(
    stmt,
    *,
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    subject=None,
    program_id=None,
    verification_status=None,
    public_only=False,
    search=None,
    season_id=None,
):
    if university_id:
        stmt = stmt.where(BenefitRule.university_id == _as_uuid(university_id))
    if olympiad_id:
        stmt = stmt.where(BenefitRule.olympiad_id == _as_uuid(olympiad_id))
    if benefit_type:
        stmt = stmt.where(
            BenefitRule.benefit_type == normalize_benefit_type(benefit_type)
        )
    if subject:
        stmt = stmt.where(BenefitRule.subject.ilike(f'%{subject}%'))
    if season_id:
        stmt = stmt.where(BenefitRule.season_id == _as_uuid(season_id))
    if verification_status:
        stmt = stmt.where(
            BenefitRule.verification_status == normalize_status(verification_status)
        )
    if public_only:
        stmt = stmt.where(
            BenefitRule.is_published.is_(True),
            BenefitRule.verification_status == 'verified',
        )
    if program_id:
        program_rule_ids = select(BenefitRuleProgram.rule_id).where(
            BenefitRuleProgram.program_id == _as_uuid(program_id)
        )
        stmt = stmt.where(BenefitRule.id.in_(program_rule_ids))
    if search:
        pattern = f'%{search.strip()}%'
        stmt = stmt.where(
            or_(
                BenefitRule.subject.ilike(pattern),
                BenefitRule.required_result.ilike(pattern),
                BenefitRule.additional_requirements.ilike(pattern),
            )
        )
    return stmt


async def get_rule(rule_id, *, public_only=False):
    async with AsyncSessionLocal() as session:
        stmt = _rule_query().where(BenefitRule.id == _as_uuid(rule_id))
        if public_only:
            stmt = stmt.where(
                BenefitRule.is_published.is_(True),
                BenefitRule.verification_status == 'verified',
            )
        result = await session.execute(stmt)
        r = result.scalar_one_or_none()
        return rule_to_dict(r) if r else None


async def list_rules(
    *,
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    subject=None,
    program_id=None,
    verification_status=None,
    public_only=False,
    search=None,
    season_id=None,
    limit=None,
    offset=0,
):
    """Вернуть ``(rules, total)`` под фильтром и страницей."""
    async with AsyncSessionLocal() as session:
        stmt = _apply_filters(
            _rule_query(),
            university_id=university_id,
            olympiad_id=olympiad_id,
            benefit_type=benefit_type,
            subject=subject,
            program_id=program_id,
            verification_status=verification_status,
            public_only=public_only,
            search=search,
            season_id=season_id,
        ).order_by(BenefitRule.createdAt.desc(), BenefitRule.id)
        count_stmt = _apply_filters(
            select(func.count()).select_from(BenefitRule),
            university_id=university_id,
            olympiad_id=olympiad_id,
            benefit_type=benefit_type,
            subject=subject,
            program_id=program_id,
            verification_status=verification_status,
            public_only=public_only,
            search=search,
            season_id=season_id,
        )
        total = int((await session.execute(count_stmt)).scalar_one())
        if limit is not None:
            stmt = stmt.limit(limit).offset(max(0, int(offset or 0)))
        result = await session.execute(stmt)
        return [rule_to_dict(r) for r in result.scalars().all()], total


async def count_rules(*, verification_status=None, public_only=False):
    async with AsyncSessionLocal() as session:
        stmt = _apply_filters(
            select(func.count()).select_from(BenefitRule),
            verification_status=verification_status,
            public_only=public_only,
        )
        return int((await session.execute(stmt)).scalar_one())


async def create_rule(data: dict, program_ids=None, user_id=None):
    async with AsyncSessionLocal() as session:
        r = BenefitRule(
            university_id=_as_uuid(data['university_id']),
            olympiad_id=_as_uuid(data['olympiad_id']),
            season_id=_as_uuid(data['season_id']) if data.get('season_id') else None,
            profile_id=_as_uuid(data['profile_id']) if data.get('profile_id') else None,
            benefit_type=normalize_benefit_type(data.get('benefit_type', 'BVI')),
            required_result=data.get('required_result'),
            required_result_type=data.get('required_result_type'),
            required_result_value=data.get('required_result_value'),
            subject=data.get('subject'),
            additional_requirements=data.get('additional_requirements'),
            doc_id=_as_uuid(data['doc_id']) if data.get('doc_id') else None,
            source_id=_as_uuid(data['source_id']) if data.get('source_id') else None,
            source_url=data.get('source_url'),
            verification_status='unverified',
            is_published=(
                True
                if data.get('is_published') is None
                else bool(data['is_published'])
            ),
            created_by=_as_uuid(user_id) if user_id else None,
            updated_by=_as_uuid(user_id) if user_id else None,
        )
        session.add(r)
        await session.flush()
        for pid in dict.fromkeys(str(p) for p in (program_ids or [])):
            session.add(BenefitRuleProgram(rule_id=r.id, program_id=_as_uuid(pid)))
        await session.flush()
        await _create_version(
            session, r, changed_by=user_id, changed_fields=['*'], reason='created'
        )
        await session.commit()
        result = await session.execute(
            _rule_query().where(BenefitRule.id == r.id)
        )
        created = result.scalar_one()
        return rule_to_dict(created)


async def _snapshot(r, program_ids):
    return {
        'id': str(r.id),
        'university_id': str(r.university_id),
        'olympiad_id': str(r.olympiad_id),
        'season_id': str(r.season_id) if r.season_id else None,
        'profile_id': str(r.profile_id) if r.profile_id else None,
        'benefit_type': r.benefit_type,
        'required_result': r.required_result,
        'required_result_type': getattr(r, 'required_result_type', None),
        'required_result_value': getattr(r, 'required_result_value', None),
        'subject': r.subject,
        'additional_requirements': r.additional_requirements,
        'program_ids': program_ids,
        'doc_id': str(r.doc_id) if r.doc_id else None,
        'source_id': str(r.source_id) if getattr(r, 'source_id', None) else None,
        'source_url': r.source_url,
        'verification_status': r.verification_status,
        'is_published': r.is_published,
        'version': r.version,
    }


async def _create_version(session, r, changed_by=None, changed_fields=None, reason=None):
    pids = [
        str(x.program_id)
        for x in (
            await session.execute(
                select(BenefitRuleProgram).where(
                    BenefitRuleProgram.rule_id == r.id
                )
            )
        ).scalars().all()
    ]
    snap = await _snapshot(r, pids)
    session.add(
        BenefitRuleVersion(
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
    )


async def update_rule(
    rule_id,
    data: dict,
    program_ids=None,
    user_id=None,
    reason=None,
    *,
    expected_version=None,
    reset_verified=True,
):
    """Обновить правило.

    Строка блокируется ``FOR UPDATE``: проверка версии и запись идут в одной
    транзакции, поэтому два параллельных PATCH не могут оба пройти проверку.
    ``None`` в ``data`` очищает необязательное поле — это часть частичного
    обновления, а не «поле не передано» (для этого есть ``exclude_unset``).
    """
    rule_uuid = _as_uuid(rule_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitRule)
            .where(BenefitRule.id == rule_uuid)
            .with_for_update()
        )
        r = result.scalar_one_or_none()
        if not r:
            return None
        if expected_version is not None and int(expected_version) != int(r.version):
            raise VersionConflict('Version conflict')

        changed = []
        for k in (
            'season_id', 'profile_id', 'benefit_type', 'required_result',
            'required_result_type', 'required_result_value', 'subject',
            'additional_requirements', 'doc_id', 'source_id', 'source_url', 'is_published',
            'rejection_reason',
        ):
            if k not in data:
                continue
            new_val = data[k]
            if k in ('season_id', 'profile_id', 'doc_id', 'source_id') and new_val:
                new_val = _as_uuid(new_val)
            if k == 'benefit_type':
                new_val = normalize_benefit_type(new_val)
            if getattr(r, k) != new_val:
                changed.append(k)
                setattr(r, k, new_val)

        if 'verification_status' in data and data['verification_status'] is not None:
            new_status = normalize_status(data['verification_status'])
            if r.verification_status != new_status:
                session.add(
                    BenefitStatusHistory(
                        rule_id=r.id,
                        from_status=r.verification_status,
                        to_status=new_status,
                        changed_by=_as_uuid(user_id) if user_id else None,
                        reason=reason,
                    )
                )
                changed.append('verification_status')
                r.verification_status = new_status

        # Набор программ — тоже содержание правила. Сравниваем с текущим:
        # PATCH с тем же набором не считается правкой и не снимает проверку.
        if program_ids is not None:
            normalized_programs = list(
                dict.fromkeys(str(pid) for pid in program_ids)
            )
            existing_programs = {
                str(pid)
                for pid in (
                    await session.execute(
                        select(BenefitRuleProgram.program_id).where(
                            BenefitRuleProgram.rule_id == r.id
                        )
                    )
                ).scalars()
            }
            if existing_programs != set(normalized_programs):
                await session.execute(
                    delete(BenefitRuleProgram).where(
                        BenefitRuleProgram.rule_id == r.id
                    )
                )
                for pid in normalized_programs:
                    session.add(
                        BenefitRuleProgram(
                            rule_id=r.id, program_id=_as_uuid(pid)
                        )
                    )
                changed.append('program_ids')

        # Любая правка содержания проверенной льготы снимает проверку: иначе
        # представитель мог бы подтвердить правило один раз, а затем менять
        # условия, оставаясь «проверенным».
        content_changed = [c for c in changed if c in _CONTENT_FIELDS]
        if (
            reset_verified
            and r.verification_status == 'verified'
            and content_changed
        ):
            session.add(
                BenefitStatusHistory(
                    rule_id=r.id,
                    from_status='verified',
                    to_status='unverified',
                    changed_by=_as_uuid(user_id) if user_id else None,
                    reason=reason or 'content changed',
                )
            )
            r.verification_status = 'unverified'
            changed.append('verification_status')

        # Пустой PATCH не создаёт новую версию: история должна отражать
        # изменения, а не факт нажатия кнопки.
        if not changed:
            await session.rollback()
            return await get_rule(rule_id)

        r.version = (r.version or 1) + 1
        r.updated_by = _as_uuid(user_id) if user_id else r.updated_by
        await session.flush()
        await _create_version(
            session,
            r,
            changed_by=user_id,
            changed_fields=changed,
            reason=reason,
        )
        await session.commit()
        result = await session.execute(
            _rule_query().where(BenefitRule.id == r.id)
        )
        updated = result.scalar_one()
        return rule_to_dict(updated)


async def set_status(
    rule_id, new_status, user_id=None, reason=None, *, expected_version=None
):
    status = normalize_status(new_status)
    data = {'verification_status': status}
    if status == 'rejected':
        data['rejection_reason'] = reason
    elif status == 'verified':
        data['rejection_reason'] = None
        data['is_published'] = True
    return await update_rule(
        rule_id,
        data,
        user_id=user_id,
        reason=reason,
        reset_verified=False,
        expected_version=expected_version,
    )


async def list_versions(rule_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitRuleVersion)
            .where(BenefitRuleVersion.rule_id == _as_uuid(rule_id))
            .order_by(BenefitRuleVersion.version_number)
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
        rresult = await session.execute(
            select(BenefitRule)
            .where(BenefitRule.id == _as_uuid(rule_id))
            .with_for_update()
        )
        r = rresult.scalar_one_or_none()
        if not r:
            return None
        snap = v.snapshot or {}
        r.season_id = _as_uuid(snap['season_id']) if snap.get('season_id') else None
        r.profile_id = _as_uuid(snap['profile_id']) if snap.get('profile_id') else None
        r.benefit_type = snap.get('benefit_type', r.benefit_type)
        r.required_result = snap.get('required_result')
        r.required_result_type = snap.get('required_result_type')
        r.required_result_value = snap.get('required_result_value')
        r.subject = snap.get('subject')
        r.additional_requirements = snap.get('additional_requirements')
        r.doc_id = _as_uuid(snap['doc_id']) if snap.get('doc_id') else None
        r.source_id = _as_uuid(snap['source_id']) if snap.get('source_id') else None
        r.source_url = snap.get('source_url')
        r.is_published = snap.get('is_published', True)
        # Восстановление контента не восстанавливает доверие: проверку
        # проходит только администратор после просмотра новой редакции.
        r.verification_status = 'unverified'
        r.rejection_reason = None
        r.version = (r.version or 1) + 1
        r.updated_by = _as_uuid(user_id) if user_id else r.updated_by
        await session.execute(
            delete(BenefitRuleProgram).where(
                BenefitRuleProgram.rule_id == r.id
            )
        )
        for pid in snap.get('program_ids') or []:
            session.add(
                BenefitRuleProgram(rule_id=r.id, program_id=_as_uuid(pid))
            )
        await session.flush()
        await _create_version(
            session,
            r,
            changed_by=user_id,
            changed_fields=['rollback'],
            reason=f'rollback to v{version_number}',
        )
        await session.commit()
        result = await session.execute(
            _rule_query().where(BenefitRule.id == r.id)
        )
        updated = result.scalar_one()
        return rule_to_dict(updated)


async def list_status_history(rule_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitStatusHistory)
            .where(BenefitStatusHistory.rule_id == _as_uuid(rule_id))
            .order_by(BenefitStatusHistory.changed_at)
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


async def count_by_status():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitRule.verification_status, func.count())
            .group_by(BenefitRule.verification_status)
        )
        return {status: int(count) for status, count in result.all()}
