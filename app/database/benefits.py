"""Слой доступа к правилам льгот.

Публичные выборки отдают опубликованные правила, кроме отклонённых: MVP
показывает непроверенные правила с предупреждением «Не проверено Papaya», а не
скрывает их. Черновик (``is_published = false``) и отклонённая запись — рабочий
материал модерации, а не факт каталога.

Фильтрация и пагинация выполняются в SQL: страница каталога не должна тянуть
весь справочник, а ответ обязан отдавать честный ``total``.
"""

import uuid as uuid_mod

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.models.benefits import (
    BENEFIT_TYPES,
    REQUIRED_RESULT_TYPES,
    BenefitEgeRequirement,
    BenefitRule,
    BenefitRuleVersion,
    BenefitStatusHistory,
)
from app.models.docs import Docs
from app.models.olympiads import Olympiads
from app.models.seasons import OlympiadSeason, SeasonProfile
from app.models.universities import Universities


class VersionConflict(Exception):
    """Версия правила изменилась между чтением и записью."""


class InvalidReference(ValueError):
    """Ссылки правила больше не существуют, чужие или противоречат модели."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def public_condition():
    """Условие публичной видимости правила (MVP).

    Непроверенное правило видно, если оно опубликовано; отклонённое не видно
    никогда. Проверка вынесена в функцию, чтобы список и получение по прямому
    id не разошлись.
    """
    return and_(
        BenefitRule.is_published.is_(True),
        BenefitRule.verification_status != 'rejected',
    )


def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _iso(v):
    return v.isoformat() if v else None


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

_RESULT_TYPE_ALIASES = {
    'победитель': 'WINNER',
    'призёр': 'PRIZE',
    'призер': 'PRIZE',
    'победитель или призёр': 'WINNER_OR_PRIZE',
    'победитель или призер': 'WINNER_OR_PRIZE',
    'winner': 'WINNER',
    'prize': 'PRIZE',
    'winner_or_prize': 'WINNER_OR_PRIZE',
}

_STATUS_ALIASES = {
    'непроверено': 'unverified',
    'не проверено': 'unverified',
    'проверено': 'verified',
    'отклонено': 'rejected',
}

#: Поля, изменение которых делает проверенную льготу снова непроверенной.
_CONTENT_FIELDS = frozenset({
    'season_id', 'profile_id', 'benefit_type', 'required_result_type',
    'doc_id', 'ege_requirement',
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
    if upper in BENEFIT_TYPES:
        return upper
    return v


def normalize_result_type(value):
    """Привести результат к структурированному значению.

    Свободный текст используется только при миграции старых записей; в новом
    API значение всегда одно из ``REQUIRED_RESULT_TYPES``.
    """
    if value is None or value == '':
        return None
    v = str(value).strip()
    key = v.lower()
    if key in _RESULT_TYPE_ALIASES:
        return _RESULT_TYPE_ALIASES[key]
    upper = v.upper()
    if upper in REQUIRED_RESULT_TYPES:
        return upper
    return v


def _ege_to_dict(req):
    if req is None:
        return None
    return {'subject': req.subject, 'min_score': req.min_score}


def _doc_to_dict(doc):
    if doc is None:
        return None
    return {
        'id': str(doc.id),
        'name': doc.name,
        'type': doc.type,
        'source_url': doc.source_url,
        'university_id': str(doc.university_id) if doc.university_id else None,
    }


def rule_to_dict(
    r,
    *,
    university_name=None,
    university_short_name=None,
    olympiad_name=None,
    season_label=None,
    profile_name=None,
    profile_rsosh_level=None,
):
    return {
        'id': str(r.id),
        'university_id': str(r.university_id),
        'university_name': university_name,
        'university_short_name': university_short_name,
        'olympiad_id': str(r.olympiad_id),
        'olympiad_name': olympiad_name,
        'season_id': str(r.season_id) if r.season_id else None,
        'season_label': season_label,
        'profile_id': str(r.profile_id) if r.profile_id else None,
        'profile_name': profile_name,
        'profile_rsosh_level': profile_rsosh_level,
        'benefit_type': r.benefit_type,
        'required_result_type': r.required_result_type,
        'ege_requirement': _ege_to_dict(getattr(r, 'ege_requirement', None)),
        'doc_id': str(r.doc_id) if r.doc_id else None,
        'doc': _doc_to_dict(getattr(r, 'doc', None)),
        'needs_review': bool(getattr(r, 'needs_review', False)),
        'verification_status': r.verification_status,
        'rejection_reason': r.rejection_reason,
        'is_published': r.is_published,
        'version': r.version,
        'created_by': str(r.created_by) if r.created_by else None,
        'updated_by': str(r.updated_by) if r.updated_by else None,
        'createdAt': _iso(r.createdAt),
        'updatedAt': _iso(r.updatedAt),
    }


def _rule_query():
    # selectinload обязателен: без него обращение к ``rule.doc`` в
    # async-сессии падает с MissingGreenlet. Названия подтягиваются JOIN-ом:
    # карточка каталога не должна делать по запросу на каждую строку.
    return (
        select(
            BenefitRule,
            Universities.name,
            Universities.short_name,
            Olympiads.name,
            OlympiadSeason.season_label,
            SeasonProfile.name,
            SeasonProfile.rsosh_level,
        )
        .join(Universities, BenefitRule.university_id == Universities.id)
        .join(Olympiads, BenefitRule.olympiad_id == Olympiads.id)
        .outerjoin(OlympiadSeason, BenefitRule.season_id == OlympiadSeason.id)
        .outerjoin(SeasonProfile, BenefitRule.profile_id == SeasonProfile.id)
        .options(
            selectinload(BenefitRule.ege_requirement),
            selectinload(BenefitRule.doc),
        )
    )


def _row_to_dict(row):
    (
        rule,
        university_name,
        university_short_name,
        olympiad_name,
        season_label,
        profile_name,
        profile_rsosh_level,
    ) = row
    return rule_to_dict(
        rule,
        university_name=university_name,
        university_short_name=university_short_name,
        olympiad_name=olympiad_name,
        season_label=season_label,
        profile_name=profile_name,
        profile_rsosh_level=profile_rsosh_level,
    )


async def _fetch_rule(session, rule_id, *, public_only=False):
    stmt = _rule_query().where(BenefitRule.id == _as_uuid(rule_id))
    if public_only:
        stmt = stmt.where(public_condition())
    result = await session.execute(stmt)
    row = result.first()
    return _row_to_dict(row) if row else None


async def verification_problem(session, rule):
    """Почему правило нельзя подтвердить, или ``None``.

    Подтверждение — это утверждение «так написано в официальном документе
    вуза». Поэтому нужен именно приказ/положение университета, привязанный к
    тому же вузу. Проверка живёт в слое данных: её нельзя обойти прямым
    вызовом ``set_status`` из другого маршрута.
    """
    if not rule.season_id:
        return 'Для подтверждения нужен сезон олимпиады'
    if not rule.profile_id:
        return 'Для подтверждения нужен профиль сезона'
    if not rule.doc_id:
        return 'Для подтверждения нужен официальный документ вуза'
    doc = await session.get(Docs, rule.doc_id)
    if doc is None:
        return 'Документ не найден'
    if doc.type != 'UNIVERSITY_ORDER':
        return 'Подтверждение возможно только по приказу или положению вуза'
    if not doc.university_id or doc.university_id != rule.university_id:
        return 'Документ должен принадлежать тому же университету'
    return None


def _apply_filters(
    stmt,
    *,
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    season_id=None,
    profile_id=None,
    level=None,
    verification_status=None,
    needs_review=None,
    public_only=False,
    search=None,
):
    if university_id:
        stmt = stmt.where(BenefitRule.university_id == _as_uuid(university_id))
    if olympiad_id:
        stmt = stmt.where(BenefitRule.olympiad_id == _as_uuid(olympiad_id))
    if benefit_type:
        stmt = stmt.where(
            BenefitRule.benefit_type == normalize_benefit_type(benefit_type)
        )
    if season_id:
        stmt = stmt.where(BenefitRule.season_id == _as_uuid(season_id))
    if profile_id:
        stmt = stmt.where(BenefitRule.profile_id == _as_uuid(profile_id))
    if level:
        stmt = stmt.where(SeasonProfile.rsosh_level == str(level))
    if needs_review is not None:
        stmt = stmt.where(BenefitRule.needs_review.is_(bool(needs_review)))
    if verification_status:
        stmt = stmt.where(
            BenefitRule.verification_status == normalize_status(verification_status)
        )
    if public_only:
        stmt = stmt.where(public_condition())
    if search:
        pattern = f'%{search.strip()}%'
        # Поиск идёт и по связанным сущностям: пользователь вводит «Физтех» и
        # ждёт олимпиаду, «МФТИ» — вуз, «2025/2026» — сезон. Подзапросы вместо
        # JOIN сохраняют однозначность count-запроса.
        stmt = stmt.where(
            or_(
                BenefitRule.university_id.in_(
                    select(Universities.id).where(
                        or_(
                            Universities.name.ilike(pattern),
                            Universities.short_name.ilike(pattern),
                        )
                    )
                ),
                BenefitRule.olympiad_id.in_(
                    select(Olympiads.id).where(Olympiads.name.ilike(pattern))
                ),
                BenefitRule.season_id.in_(
                    select(OlympiadSeason.id).where(
                        OlympiadSeason.season_label.ilike(pattern)
                    )
                ),
                BenefitRule.profile_id.in_(
                    select(SeasonProfile.id).where(
                        SeasonProfile.name.ilike(pattern)
                    )
                ),
            )
        )
    return stmt


async def get_rule(rule_id, *, public_only=False):
    async with AsyncSessionLocal() as session:
        return await _fetch_rule(session, rule_id, public_only=public_only)


def _filter_kwargs(
    *,
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    season_id=None,
    profile_id=None,
    level=None,
    verification_status=None,
    needs_review=None,
    public_only=False,
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
        'public_only': public_only,
        'search': search,
    }


async def list_rules(
    *,
    university_id=None,
    olympiad_id=None,
    benefit_type=None,
    season_id=None,
    profile_id=None,
    level=None,
    verification_status=None,
    needs_review=None,
    public_only=False,
    search=None,
    limit=None,
    offset=0,
):
    """Вернуть ``(rules, total)`` под фильтром и страницей."""
    kwargs = _filter_kwargs(
        university_id=university_id,
        olympiad_id=olympiad_id,
        benefit_type=benefit_type,
        season_id=season_id,
        profile_id=profile_id,
        level=level,
        verification_status=verification_status,
        needs_review=needs_review,
        public_only=public_only,
        search=search,
    )
    async with AsyncSessionLocal() as session:
        stmt = _apply_filters(_rule_query(), **kwargs).order_by(
            BenefitRule.createdAt.desc(), BenefitRule.id
        )
        count_stmt = select(func.count()).select_from(BenefitRule)
        # Условие по уровню обращается к профилю: без JOIN count не соберётся.
        if level:
            count_stmt = count_stmt.join(
                SeasonProfile, BenefitRule.profile_id == SeasonProfile.id
            )
        count_stmt = _apply_filters(count_stmt, **kwargs)
        total = int((await session.execute(count_stmt)).scalar_one())
        if limit is not None:
            stmt = stmt.limit(limit).offset(max(0, int(offset or 0)))
        result = await session.execute(stmt)
        return [_row_to_dict(row) for row in result.all()], total


async def count_rules(*, verification_status=None, public_only=False):
    async with AsyncSessionLocal() as session:
        stmt = _apply_filters(
            select(func.count()).select_from(BenefitRule),
            verification_status=verification_status,
            public_only=public_only,
        )
        return int((await session.execute(stmt)).scalar_one())


async def list_universities_for_olympiad(olympiad_id):
    """Университеты с публичными правилами по олимпиаде.

    Список строится по правилам, а не по отдельной таблице связей: одна
    модель данных не может разойтись сама с собой.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                Universities.id,
                Universities.name,
                Universities.short_name,
                Universities.website,
                Universities.preview_image,
                Universities.image,
            )
            .join(BenefitRule, BenefitRule.university_id == Universities.id)
            .where(
                BenefitRule.olympiad_id == _as_uuid(olympiad_id),
                public_condition(),
            )
            .distinct()
            .order_by(Universities.name)
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                'id': str(row[0]),
                'name': row[1],
                'short_name': row[2],
                'website': row[3],
                'preview_image': row[4],
                'image': row[5],
            }
            for row in rows
        ]


async def _upsert_ege(session, rule, ege):
    """Синхронизировать необязательное требование ЕГЭ."""
    existing = (
        await session.execute(
            select(BenefitEgeRequirement).where(
                BenefitEgeRequirement.rule_id == rule.id
            )
        )
    ).scalar_one_or_none()
    if not ege:
        if existing is not None:
            await session.delete(existing)
            await session.flush()
        return
    subject = (ege.get('subject') or '').strip()
    if not subject:
        raise InvalidReference('Требование ЕГЭ: укажите предмет')
    min_score = ege.get('min_score')
    if min_score is not None:
        min_score = int(min_score)
        if min_score < 0 or min_score > 100:
            raise InvalidReference('Минимальный балл ЕГЭ должен быть от 0 до 100')
    if existing is None:
        session.add(
            BenefitEgeRequirement(
                rule_id=rule.id, subject=subject, min_score=min_score
            )
        )
    else:
        existing.subject = subject
        existing.min_score = min_score
    await session.flush()


async def create_rule(data: dict, user_id=None):
    async with AsyncSessionLocal() as session:
        r = BenefitRule(
            university_id=_as_uuid(data['university_id']),
            olympiad_id=_as_uuid(data['olympiad_id']),
            season_id=_as_uuid(data['season_id']) if data.get('season_id') else None,
            profile_id=(
                _as_uuid(data['profile_id']) if data.get('profile_id') else None
            ),
            benefit_type=normalize_benefit_type(data.get('benefit_type', 'BVI')),
            required_result_type=normalize_result_type(
                data.get('required_result_type')
            ),
            doc_id=_as_uuid(data['doc_id']) if data.get('doc_id') else None,
            needs_review=bool(data.get('needs_review', False)),
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
        await _upsert_ege(session, r, data.get('ege_requirement'))
        await _create_version(
            session, r, changed_by=user_id, changed_fields=['*'], reason='created'
        )
        await session.commit()
        return await _fetch_rule(session, r.id)


def _snapshot(r, ege=None):
    return {
        'id': str(r.id),
        'university_id': str(r.university_id),
        'olympiad_id': str(r.olympiad_id),
        'season_id': str(r.season_id) if r.season_id else None,
        'profile_id': str(r.profile_id) if r.profile_id else None,
        'benefit_type': r.benefit_type,
        'required_result_type': r.required_result_type,
        'ege_requirement': _ege_to_dict(ege),
        'doc_id': str(r.doc_id) if r.doc_id else None,
        'verification_status': r.verification_status,
        'is_published': r.is_published,
        'needs_review': bool(r.needs_review),
        'version': r.version,
    }


async def _create_version(session, r, changed_by=None, changed_fields=None, reason=None):
    # Требование ЕГЭ читается запросом, а не ленивой связью: после ``flush``
    # обращение к relationship в async-сессии падает с MissingGreenlet, а
    # снимок версии обязан содержать актуальное значение.
    ege = (
        await session.execute(
            select(BenefitEgeRequirement).where(
                BenefitEgeRequirement.rule_id == r.id
            )
        )
    ).scalar_one_or_none()
    session.add(
        BenefitRuleVersion(
            rule_id=r.id,
            version_number=r.version,
            snapshot=_snapshot(r, ege),
            changed_fields=changed_fields or [],
            change_reason=reason,
            verification_status=r.verification_status,
            doc_id=r.doc_id,
            changed_by=_as_uuid(changed_by) if changed_by else None,
        )
    )


async def update_rule(
    rule_id,
    data: dict,
    user_id=None,
    reason=None,
    *,
    expected_version=None,
    reset_verified=True,
    require_verification_support=False,
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

        new_status = (
            normalize_status(data['verification_status'])
            if data.get('verification_status') is not None
            else None
        )
        if new_status == 'verified' and require_verification_support:
            problem = await verification_problem(session, r)
            if problem:
                raise InvalidReference(problem)

        changed = []
        for k in (
            'season_id', 'profile_id', 'benefit_type', 'required_result_type',
            'doc_id', 'is_published', 'rejection_reason', 'needs_review',
        ):
            if k not in data:
                continue
            new_val = data[k]
            if k in ('season_id', 'profile_id', 'doc_id') and new_val:
                new_val = _as_uuid(new_val)
            if k == 'benefit_type':
                new_val = normalize_benefit_type(new_val)
            if k == 'required_result_type':
                new_val = normalize_result_type(new_val)
            if getattr(r, k) != new_val:
                changed.append(k)
                setattr(r, k, new_val)

        if 'ege_requirement' in data:
            before = _ege_to_dict(
                (
                    await session.execute(
                        select(BenefitEgeRequirement).where(
                            BenefitEgeRequirement.rule_id == r.id
                        )
                    )
                ).scalar_one_or_none()
            )
            await _upsert_ege(session, r, data['ege_requirement'])
            await session.refresh(r, attribute_names=['ege_requirement'])
            if before != _ege_to_dict(r.ege_requirement):
                changed.append('ege_requirement')

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
        return await _fetch_rule(session, r.id)


async def set_status(
    rule_id, new_status, user_id=None, reason=None, *, expected_version=None
):
    status = normalize_status(new_status)
    data = {'verification_status': status}
    if status == 'rejected':
        data['rejection_reason'] = reason
        # Отклонённая льгота не должна оставаться в публичном каталоге.
        data['is_published'] = False
    elif status == 'verified':
        data['rejection_reason'] = None
        data['is_published'] = True
        data['needs_review'] = False
    return await update_rule(
        rule_id,
        data,
        user_id=user_id,
        reason=reason,
        reset_verified=False,
        expected_version=expected_version,
        require_verification_support=status == 'verified',
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
                'changed_by': str(v.changed_by) if v.changed_by else None,
                'changed_at': _iso(v.changed_at),
            }
            for v in versions
        ]


async def _validate_snapshot_refs(session, rule, snap):
    """Проверить, что ссылки из снимка ещё существуют и принадлежат правилу."""
    season_id = snap.get('season_id')
    profile_id = snap.get('profile_id')

    if season_id:
        season = await session.get(OlympiadSeason, _as_uuid(season_id))
        if season is None:
            raise InvalidReference('Сезон из версии больше не существует')
        if season.olympiad_id != rule.olympiad_id:
            raise InvalidReference('Сезон из версии относится к другой олимпиаде')

    if profile_id:
        profile = await session.get(SeasonProfile, _as_uuid(profile_id))
        if profile is None:
            raise InvalidReference('Профиль из версии больше не существует')
        if not season_id or profile.season_id != _as_uuid(season_id):
            raise InvalidReference('Профиль из версии относится к другому сезону')

    doc_id = snap.get('doc_id')
    if doc_id:
        doc = await session.get(Docs, _as_uuid(doc_id))
        if doc is None:
            raise InvalidReference('Документ из версии больше не существует')
        if doc.university_id != rule.university_id:
            raise InvalidReference(
                'Документ из версии относится к другому университету'
            )


async def rollback(rule_id, version_number, user_id=None, *, expected_version=None):
    """Восстановить содержимое версии как новую версию.

    Строка правила блокируется до чтения снимка: проверка ожидаемой версии и
    запись идут в одной транзакции, поэтому параллельный PATCH не может
    проскочить между ними. Откат никогда не возвращает ``verified``: доверие
    к правилу выдаётся администратором заново, а не наследуется от старой
    редакции.
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

        v = (
            await session.execute(
                select(BenefitRuleVersion).where(
                    BenefitRuleVersion.rule_id == rule_uuid,
                    BenefitRuleVersion.version_number == version_number,
                )
            )
        ).scalar_one_or_none()
        if not v:
            return None

        snap = v.snapshot or {}
        await _validate_snapshot_refs(session, r, snap)

        r.season_id = _as_uuid(snap['season_id']) if snap.get('season_id') else None
        r.profile_id = _as_uuid(snap['profile_id']) if snap.get('profile_id') else None
        r.benefit_type = normalize_benefit_type(
            snap.get('benefit_type', r.benefit_type)
        )
        r.required_result_type = normalize_result_type(
            snap.get('required_result_type')
        )
        r.doc_id = _as_uuid(snap['doc_id']) if snap.get('doc_id') else None
        r.is_published = snap.get('is_published', True)
        r.needs_review = bool(snap.get('needs_review', False))
        await _upsert_ege(session, r, snap.get('ege_requirement'))
        # Восстановление контента не восстанавливает доверие: проверку
        # проходит только администратор после просмотра новой редакции.
        if r.verification_status != 'unverified':
            session.add(
                BenefitStatusHistory(
                    rule_id=r.id,
                    from_status=r.verification_status,
                    to_status='unverified',
                    changed_by=_as_uuid(user_id) if user_id else None,
                    reason=f'rollback to v{version_number}',
                )
            )
        r.verification_status = 'unverified'
        r.rejection_reason = None
        r.version = (r.version or 1) + 1
        r.updated_by = _as_uuid(user_id) if user_id else r.updated_by
        await session.flush()
        await _create_version(
            session,
            r,
            changed_by=user_id,
            changed_fields=['rollback'],
            reason=f'rollback to v{version_number}',
        )
        await session.commit()
        return await _fetch_rule(session, r.id)


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
