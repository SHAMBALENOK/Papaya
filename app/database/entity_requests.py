"""Слой запросов на отсутствующие сущности каталога.

Запросы не создают сущности сами: одобрение выполняет администратор, а
создание идёт одной транзакцией вместе с отметкой запроса. Так не бывает
«запрос одобрен, а сезон не создан» или двух сезонов по одному запросу.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.models.entity_requests import EntityRequest
from app.models.olympiads import Olympiads
from app.models.seasons import OlympiadSeason, SeasonProfile


def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _iso(v):
    return v.isoformat() if v else None


def _parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def request_to_dict(r):
    return {
        'id': str(r.id),
        'entity_type': r.entity_type,
        'name': r.name,
        'description': r.description,
        'payload': r.payload,
        'university_id': str(r.university_id) if r.university_id else None,
        'parent_id': str(r.parent_id) if r.parent_id else None,
        'status': r.status,
        'reviewed_by': str(r.reviewed_by) if r.reviewed_by else None,
        'reviewed_at': _iso(r.reviewed_at),
        'rejection_reason': r.rejection_reason,
        'created_entity_id': (
            str(r.created_entity_id) if r.created_entity_id else None
        ),
        'created_by': str(r.created_by) if r.created_by else None,
        'createdAt': _iso(r.createdAt),
        'updatedAt': _iso(r.updatedAt),
    }


class RequestError(ValueError):
    """Запрос нельзя создать или обработать."""

    def __init__(self, detail: str, *, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class DuplicateEntity(RequestError):
    """Похожая сущность уже есть в каталоге."""

    def __init__(self, detail: str, existing_id=None):
        super().__init__(detail, status_code=409)
        self.existing_id = str(existing_id) if existing_id else None


async def _find_pending_duplicate(session, data):
    """Тот же запрос уже ждёт рассмотрения — второй не нужен."""
    statement = select(EntityRequest).where(
        EntityRequest.status == 'pending',
        EntityRequest.entity_type == data['entity_type'],
        func.lower(EntityRequest.name) == data['name'].strip().lower(),
    )
    if data.get('university_id'):
        statement = statement.where(
            EntityRequest.university_id == _as_uuid(data['university_id'])
        )
    if data.get('parent_id'):
        statement = statement.where(
            EntityRequest.parent_id == _as_uuid(data['parent_id'])
        )
    else:
        statement = statement.where(EntityRequest.parent_id.is_(None))
    result = await session.execute(statement.limit(1))
    return result.scalar_one_or_none()


async def create_request(data: dict, user_id=None) -> dict:
    async with AsyncSessionLocal() as session:
        existing = await _find_pending_duplicate(session, data)
        if existing is not None:
            return request_to_dict(existing)
        request = EntityRequest(
            entity_type=data['entity_type'],
            name=data['name'].strip(),
            description=(data.get('description') or '').strip() or None,
            payload=data.get('payload'),
            university_id=(
                _as_uuid(data['university_id'])
                if data.get('university_id') else None
            ),
            parent_id=(
                _as_uuid(data['parent_id']) if data.get('parent_id') else None
            ),
            created_by=_as_uuid(user_id) if user_id else None,
        )
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request_to_dict(request)


async def get_request(request_id) -> dict | None:
    async with AsyncSessionLocal() as session:
        request = await session.get(EntityRequest, _as_uuid(request_id))
        return request_to_dict(request) if request else None


async def list_requests(
    *,
    university_id=None,
    status=None,
    entity_type=None,
    search=None,
    limit=None,
    offset=0,
):
    statement = select(EntityRequest)
    count_statement = select(func.count()).select_from(EntityRequest)
    conditions = []
    if university_id:
        conditions.append(EntityRequest.university_id == _as_uuid(university_id))
    if status:
        conditions.append(EntityRequest.status == status)
    if entity_type:
        conditions.append(EntityRequest.entity_type == entity_type)
    if search:
        pattern = f'%{search.strip()}%'
        conditions.append(
            or_(
                EntityRequest.name.ilike(pattern),
                EntityRequest.description.ilike(pattern),
            )
        )
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    async with AsyncSessionLocal() as session:
        total = int((await session.execute(count_statement)).scalar_one())
        statement = statement.order_by(
            EntityRequest.createdAt.desc(), EntityRequest.id
        )
        if limit is not None:
            statement = statement.limit(limit).offset(max(0, int(offset or 0)))
        rows = (await session.execute(statement)).scalars().all()
        return [request_to_dict(r) for r in rows], total


def _profile_key(payload: dict) -> str:
    return normalize_name(payload.get('name') or '')


async def _create_entity(session, request):
    """Создать сущность по одобренному запросу, проверив дубли.

    Возвращает ORM-объект созданной сущности. Дубли ищутся в той же
    транзакции, что и вставка: проверка «до» без блокировки не спасает от
    параллельного одобрения.
    """
    payload = request.payload or {}

    if request.entity_type == 'OLYMPIAD':
        name = request.name.strip()
        name_norm = normalize_name(name)
        existing = (
            await session.execute(
                select(Olympiads.id).where(Olympiads.name_norm == name_norm)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateEntity(
                'Олимпиада с таким названием уже есть в каталоге', existing
            )
        entity = Olympiads(
            name=name,
            name_norm=name_norm,
            description=request.description,
            official_url=payload.get('official_url'),
            organizer=(payload.get('organizer') or '').strip() or None,
            status='PUBLISHED',
        )
        session.add(entity)
        await session.flush()
        return entity

    if request.entity_type == 'SEASON':
        if not request.parent_id:
            raise RequestError('Для сезона нужна олимпиада')
        olympiad = await session.get(Olympiads, request.parent_id)
        if olympiad is None:
            raise RequestError('Олимпиада из запроса не найдена', status_code=404)
        label = request.name.strip()
        existing = (
            await session.execute(
                select(OlympiadSeason.id).where(
                    OlympiadSeason.olympiad_id == request.parent_id,
                    func.lower(OlympiadSeason.season_label) == label.lower(),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateEntity(
                'Такой сезон у олимпиады уже есть', existing
            )
        entity = OlympiadSeason(
            olympiad_id=request.parent_id,
            season_label=label,
        )
        session.add(entity)
        await session.flush()
        return entity

    if request.entity_type == 'PROFILE':
        if not request.parent_id:
            raise RequestError('Для профиля нужен сезон')
        season = await session.get(OlympiadSeason, request.parent_id)
        if season is None:
            raise RequestError('Сезон из запроса не найден', status_code=404)
        name = request.name.strip()
        wanted = _profile_key({'name': name})
        existing = (
            await session.execute(
                select(SeasonProfile.id).where(
                    SeasonProfile.season_id == request.parent_id,
                    SeasonProfile.name_norm == wanted,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateEntity('Такой профиль у сезона уже есть', existing)
        entity = SeasonProfile(
            season_id=request.parent_id,
            name=name,
            name_norm=wanted,
            rsosh_level=payload.get('rsosh_level'),
            description=request.description,
        )
        session.add(entity)
        await session.flush()
        return entity

    raise RequestError('Неизвестный тип сущности')


async def approve_request(request_id, *, admin_id=None) -> dict:
    """Одобрить запрос: создать сущность и закрыть запрос одной транзакцией."""
    async with AsyncSessionLocal() as session:
        request = (
            await session.execute(
                select(EntityRequest)
                .where(EntityRequest.id == _as_uuid(request_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if request is None:
            raise RequestError('Запрос не найден', status_code=404)
        if request.status != 'pending':
            raise RequestError('Запрос уже рассмотрен', status_code=409)
        entity = await _create_entity(session, request)
        request.status = 'approved'
        request.reviewed_by = _as_uuid(admin_id) if admin_id else None
        request.reviewed_at = datetime.now(timezone.utc)
        request.created_entity_id = entity.id
        await session.commit()
        return {
            'request': request_to_dict(request),
            'entity_id': str(entity.id),
        }


async def reject_request(
    request_id, *, reason: str, admin_id=None
) -> dict:
    async with AsyncSessionLocal() as session:
        request = (
            await session.execute(
                select(EntityRequest)
                .where(EntityRequest.id == _as_uuid(request_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if request is None:
            raise RequestError('Запрос не найден', status_code=404)
        if request.status != 'pending':
            raise RequestError('Запрос уже рассмотрен', status_code=409)
        request.status = 'rejected'
        request.rejection_reason = reason
        request.reviewed_by = _as_uuid(admin_id) if admin_id else None
        request.reviewed_at = datetime.now(timezone.utc)
        await session.commit()
        return request_to_dict(request)
