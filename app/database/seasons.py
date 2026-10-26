"""Слой доступа к сезонам и профилям олимпиад (ТЗ §4.2, §4.4).

Олимпиада и сезон — разные сущности. Сезон несёт уровень РСОШ, даты, состояние
и профили конкретного года. Автоматически «актуальный» сезон не вычисляется:
состояние (``state``) задаётся явно, потому что «самый новый год» не значит
«сезон опубликован и идёт».

Архив сезонов: старые сезоны остаются в БД и отдаются отдельным списком, чтобы
прошлогодние даты и профили не терялись при наступлении нового года.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.middlewares.serializers import profile_to_dict, season_to_dict
from app.models.seasons import OlympiadProfile, OlympiadSeason

#: Допустимые состояния сезона. ``unknown`` — состояние ещё не определено;
#: ``upcoming`` — сезон объявлен, но не начался; ``active`` — идёт;
#: ``completed`` — завершён (прошлый сезон, архив).
SEASON_STATES = ('unknown', 'upcoming', 'active', 'completed')


class SeasonError(ValueError):
    """Сезон нельзя создать/изменить с переданными значениями."""

    def __init__(self, detail: str, *, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def list_seasons(olympiad_id, *, include_profiles: bool = True) -> list[dict]:
    """Сезоны олимпиады — от нового года к старому.

    Профили сезона едут вместе с сезоном: на публичной странице олимпиады
    профиль — часть описания сезона, и подгружать его отдельным запросом
    незачем. Профили всех сезонов берутся одним запросом, чтобы не было
    «N+1» на странице.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OlympiadSeason)
            .where(OlympiadSeason.olympiad_id == _as_uuid(olympiad_id))
            .order_by(OlympiadSeason.year.desc(), OlympiadSeason.id)
        )
        seasons = result.scalars().all()
        items = [season_to_dict(item) for item in seasons]
        if not include_profiles or not seasons:
            return items

        profiles_result = await session.execute(
            select(OlympiadProfile)
            .where(OlympiadProfile.season_id.in_([item.id for item in seasons]))
            .order_by(OlympiadProfile.name_norm, OlympiadProfile.id)
        )
        grouped: dict = {}
        for profile in profiles_result.scalars().all():
            grouped.setdefault(str(profile.season_id), []).append(
                profile_to_dict(profile)
            )
        for item in items:
            item['profiles'] = grouped.get(str(item['id']), [])
        return items


async def get_season(season_id) -> dict | None:
    """Найти сезон по id вместе с профилями."""
    async with AsyncSessionLocal() as session:
        season = (
            await session.execute(
                select(OlympiadSeason).where(OlympiadSeason.id == _as_uuid(season_id))
            )
        ).scalar_one_or_none()
        if season is None:
            return None
        profiles = (
            await session.execute(
                select(OlympiadProfile)
                .where(OlympiadProfile.season_id == season.id)
                .order_by(OlympiadProfile.name_norm, OlympiadProfile.id)
            )
        ).scalars().all()
        return {
            **season_to_dict(season),
            'profiles': [profile_to_dict(item) for item in profiles],
        }


async def upsert_season(
    olympiad_id,
    *,
    year: int,
    label: str | None = None,
    rsoh_level: str | None = None,
    state: str = 'unknown',
    dates: dict | None = None,
    description: str | None = None,
    source_url: str | None = None,
) -> dict:
    """Создать или обновить сезон олимпиады по году.

    Один сезон на пару (олимпиада, год): повторный вызов обновляет запись, а не
    создаёт вторую. Состояние валидируется по списку допустимых.
    """
    if state not in SEASON_STATES:
        raise SeasonError(
            'Недопустимое состояние сезона. Разрешены: '
            + ', '.join(SEASON_STATES)
            + '.'
        )
    olympiad_uuid = _as_uuid(olympiad_id)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        season = (
            await session.execute(
                select(OlympiadSeason).where(
                    OlympiadSeason.olympiad_id == olympiad_uuid,
                    OlympiadSeason.year == year,
                )
            )
        ).scalar_one_or_none()
        if season is None:
            season = OlympiadSeason(
                olympiad_id=olympiad_uuid,
                year=year,
                label=(label or '').strip() or None,
                rsoh_level=rsoh_level,
                state=state,
                dates=dates,
                description=description,
                source_url=source_url,
            )
            session.add(season)
        else:
            if label is not None:
                season.label = label.strip() or None
            if rsoh_level is not None:
                season.rsoh_level = rsoh_level
            season.state = state
            season.dates = dates
            if description is not None:
                season.description = description
            if source_url is not None:
                season.source_url = source_url
            season.updatedAt = now
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise SeasonError('Сезон с таким годом уже существует', status_code=409)
        await session.refresh(season)
        return season_to_dict(season)


async def archive_season(season_id) -> dict | None:
    """Пометить сезон завершённым (перенести в архив)."""
    return await _set_season_state(season_id, 'completed')


async def _set_season_state(season_id, state: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        season = (
            await session.execute(
                select(OlympiadSeason).where(OlympiadSeason.id == _as_uuid(season_id))
            )
        ).scalar_one_or_none()
        if season is None:
            return None
        season.state = state
        season.updatedAt = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(season)
        return season_to_dict(season)


async def list_profiles(season_id) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OlympiadProfile)
            .where(OlympiadProfile.season_id == _as_uuid(season_id))
            .order_by(OlympiadProfile.name_norm, OlympiadProfile.id)
        )
        return [profile_to_dict(item) for item in result.scalars().all()]


async def add_profile(
    season_id,
    *,
    name: str,
    subject: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Добавить профиль в сезон. Дубликат внутри сезона → ``None``."""
    name = (name or '').strip()
    name_norm = normalize_name(name)
    if not name_norm:
        return None
    profile = OlympiadProfile(
        season_id=_as_uuid(season_id),
        name=name,
        name_norm=name_norm,
        subject=subject,
        description=description,
    )
    async with AsyncSessionLocal() as session:
        session.add(profile)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(profile)
        return profile_to_dict(profile)


async def edit_profile(
    season_id,
    profile_id,
    *,
    name: str | None = None,
    subject: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Изменить профиль сезона; дубликат названия внутри сезона → ``SeasonError``."""
    async with AsyncSessionLocal() as session:
        profile = (
            await session.execute(
                select(OlympiadProfile).where(
                    OlympiadProfile.id == _as_uuid(profile_id),
                    OlympiadProfile.season_id == _as_uuid(season_id),
                )
            )
        ).scalar_one_or_none()
        if profile is None:
            return None
        if name is not None:
            cleaned = name.strip()
            name_norm = normalize_name(cleaned)
            if not name_norm:
                raise SeasonError('Название профиля не может быть пустым', status_code=400)
            profile.name = cleaned
            profile.name_norm = name_norm
        if subject is not None:
            profile.subject = subject.strip() or None
        if description is not None:
            profile.description = description.strip() or None
        profile.updatedAt = datetime.now(timezone.utc)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise SeasonError(
                'Профиль с таким названием уже есть в этом сезоне', status_code=409
            )
        await session.refresh(profile)
        return profile_to_dict(profile)


async def remove_profile(season_id, profile_id) -> bool:
    """Удалить профиль сезона.

    Профиль, на который ссылаются правила льгот, удалить нельзя (внешний ключ
    ``benefit_rules.profile_id``): сначала правила нужно перевести на другой
    профиль. Иначе правило молча потеряло бы свою область действия.
    """
    async with AsyncSessionLocal() as session:
        profile = (
            await session.execute(
                select(OlympiadProfile).where(
                    OlympiadProfile.id == _as_uuid(profile_id),
                    OlympiadProfile.season_id == _as_uuid(season_id),
                )
            )
        ).scalar_one_or_none()
        if profile is None:
            return False
        await session.delete(profile)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise SeasonError(
                'Профиль используется в правилах льгот: сначала уберите его из правил',
                status_code=409,
            )
        return True
