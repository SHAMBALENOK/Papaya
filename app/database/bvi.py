"""Слой доступа к связи «университет даёт БВИ за олимпиаду».

Связь читается в обе стороны: по университету получаем олимпиады, по
олимпиаде — университеты. Возвращаются готовые словари каталога, поэтому
страница университета и страница олимпиады строятся одинаково, а фронтенду
не нужно знать про таблицу ``university_olympiads``.

Инварианты, которые держит этот модуль:

- одна пара (университет, олимпиада) — одна связь (уникальный индекс в БД),
  поэтому «две одинаковые связи» невозможны даже напрямую в базе;
- университет **не создаёт олимпиаду**: здесь только ссылки на существующие
  записи каталога;
- заявка представителя (``PENDING``) не видна в публичных списках: там только
  подтверждённые администратором связи (``CONFIRMED``).
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import (
    bvi_link_to_dict,
    olympiad_to_dict,
    university_to_dict,
)
from app.models.bvi import UniversityBvi
from app.models.olympiads import Olympiads
from app.models.universities import Universities


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def get_link(olympiad_id, university_id) -> dict | None:
    """Найти конкретную связь по паре id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UniversityBvi).where(
                UniversityBvi.olympiad_id == _as_uuid(olympiad_id),
                UniversityBvi.university_id == _as_uuid(university_id),
            )
        )
        link = result.scalar_one_or_none()
        return bvi_link_to_dict(link) if link else None


async def list_links(
    *,
    university_id=None,
    olympiad_id=None,
    status: str | None = None,
) -> list[dict]:
    """Список связей с фильтрами (очередь модерации и проверки)."""
    statement = select(UniversityBvi)
    if university_id is not None:
        statement = statement.where(
            UniversityBvi.university_id == _as_uuid(university_id)
        )
    if olympiad_id is not None:
        statement = statement.where(
            UniversityBvi.olympiad_id == _as_uuid(olympiad_id)
        )
    if status is not None:
        statement = statement.where(UniversityBvi.status == status)
    statement = statement.order_by(UniversityBvi.createdAt, UniversityBvi.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [bvi_link_to_dict(link) for link in result.scalars().all()]


async def list_olympiads_for_university(
    university_id,
    *,
    include_pending: bool = False,
) -> list[dict]:
    """Олимпиады, дающие БВИ в университете (по умолчанию — подтверждённые).

    JOIN по ``olympiads`` отсекает связи на несуществующие олимпиады: FK
    защищает от «висячих» id после ручных правок БД.
    """
    statement = (
        select(Olympiads, UniversityBvi.status)
        .join(UniversityBvi, UniversityBvi.olympiad_id == Olympiads.id)
        .where(UniversityBvi.university_id == _as_uuid(university_id))
        .order_by(Olympiads.name_norm, Olympiads.id)
    )
    if not include_pending:
        statement = statement.where(UniversityBvi.status == 'CONFIRMED')

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [
            {
                **olympiad_to_dict(olympiad),
                'bvi_status': status,
                # Связь историческая, если олимпиады больше нет в актуальном
                # перечне. Саму связь не удаляем: университет действительно давал
                # БВИ, пока олимпиада была актуальной.
                'is_historical': olympiad.status != 'PUBLISHED',
            }
            for olympiad, status in result.all()
        ]


async def list_universities_for_olympiad(
    olympiad_id,
    *,
    include_pending: bool = False,
) -> list[dict]:
    """Университеты, дающие БВИ за олимпиаду (обратная сторона связи)."""
    statement = (
        select(Universities, UniversityBvi.status)
        .join(UniversityBvi, UniversityBvi.university_id == Universities.id)
        .where(UniversityBvi.olympiad_id == _as_uuid(olympiad_id))
        .order_by(Universities.name_norm, Universities.id)
    )
    if not include_pending:
        statement = statement.where(UniversityBvi.status == 'CONFIRMED')

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        olympiad = (
            await session.execute(
                select(Olympiads.status).where(Olympiads.id == _as_uuid(olympiad_id))
            )
        ).scalar_one_or_none()
        # Обратная сторона: олимпиада одна, поэтому историчность связи
        # одинакова для всех университетов в списке.
        is_historical = olympiad != 'PUBLISHED'
        return [
            {
                **university_to_dict(university),
                'bvi_status': status,
                'is_historical': is_historical,
            }
            for university, status in result.all()
        ]


async def request_bvi_link(
    olympiad_id,
    university_id,
    *,
    requested_by=None,
) -> dict:
    """Подать заявку «этот университет даёт БВИ за эту олимпиаду».

    Идемпотентно: если связь уже есть (в любом статусе), она возвращается без
    изменения. Повторная заявка после подтверждения не сбрасывает статус на
    ``PENDING`` — иначе представитель мог бы «разжаловать» подтверждённую
    связь одной повторной заявкой.
    """
    olympiad_uuid = _as_uuid(olympiad_id)
    university_uuid = _as_uuid(university_id)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UniversityBvi).where(
                UniversityBvi.olympiad_id == olympiad_uuid,
                UniversityBvi.university_id == university_uuid,
            )
        )
        link = result.scalar_one_or_none()
        if link:
            return bvi_link_to_dict(link)

        link = UniversityBvi(
            university_id=university_uuid,
            olympiad_id=olympiad_uuid,
            status='PENDING',
            createdBy=_as_uuid(requested_by) if requested_by else None,
            createdAt=now,
            updatedAt=now,
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
        return bvi_link_to_dict(link)


#: Что делает действие модерации: подтвердить заявку или убрать связь.
MODERATION_CONFIRM = 'confirm'
MODERATION_REJECT = 'reject'
MODERATION_REVOKE = 'revoke'

MODERATION_ACTIONS = (
    MODERATION_CONFIRM,
    MODERATION_REJECT,
    MODERATION_REVOKE,
)


class BviModerationError(ValueError):
    """Действие модерации неприменимо к связи в её текущем состоянии.

    Текст сообщения отдаётся HTTP-слоем как 409, поэтому он должен объяснять
    ситуацию администратору, а не сообщать код ошибки базы.
    """


async def moderate_bvi_link(
    olympiad_id,
    university_id,
    action: str,
    *,
    admin_id=None,
) -> dict | None:
    """Административное действие над заявкой БВИ.

    Три действия и только три:

    - ``confirm`` (``PENDING`` → ``CONFIRMED``) — подтвердить заявку;
    - ``reject`` (``PENDING`` → удаление) — отклонить заявку;
    - ``revoke`` (``CONFIRMED`` → удаление) — отозвать подтверждение.

    Возврата ``CONFIRMED`` → ``PENDING`` здесь нет намеренно. Такой переход
    создаёт запись, которая в публичном каталоге не показывается (связь не
    подтверждена), а в очереди модерации видна как заявка, будто университет
    её повторно подал. Отзыв подтверждения — это удаление связи, после
    которого университет может подать новую заявку заново, и её видно в
    очереди как новую.

    Возвращает ``{'result': 'CONFIRMED'|'removed'}``; ``None``, если связи нет.
    """
    if action not in MODERATION_ACTIONS:
        raise ValueError(f'Unsupported BVI moderation action: {action}')

    olympiad_uuid = _as_uuid(olympiad_id)
    university_uuid = _as_uuid(university_id)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UniversityBvi).where(
                UniversityBvi.olympiad_id == olympiad_uuid,
                UniversityBvi.university_id == university_uuid,
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            return None

        if action == MODERATION_CONFIRM:
            if link.status == 'CONFIRMED':
                raise BviModerationError(
                    'Связь уже подтверждена.'
                )
            if not admin_id:
                raise ValueError('CONFIRMED BVI link requires admin_id')
            link.status = 'CONFIRMED'
            # Автор подтверждения существует только у CONFIRMED: у PENDING его
            # быть не должно, иначе по записи нельзя понять, кто отвечает за
            # связь.
            link.confirmedBy = _as_uuid(admin_id)
            link.updatedAt = now
            await session.commit()
            await session.refresh(link)
            return {'result': 'CONFIRMED', 'link': bvi_link_to_dict(link)}

        # reject/revoke: связь удаляется целиком. Отклонённая и отозванная
        # связь не должна висеть ни в публичном каталоге, ни в очереди.
        if action == MODERATION_REJECT and link.status != 'PENDING':
            raise BviModerationError(
                'Отклонить можно только заявку, ещё не подтверждённую. '
                'Подтверждённую связь отзывают через «Отозвать подтверждение».'
            )
        if action == MODERATION_REVOKE and link.status != 'CONFIRMED':
            raise BviModerationError(
                'Отозвать подтверждение можно только у подтверждённой связи.'
            )
        await session.delete(link)
        await session.commit()
        return {'result': 'removed', 'link': None}


async def delete_bvi_link(olympiad_id, university_id) -> bool:
    """Удалить связь целиком (и заявку, и подтверждение)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UniversityBvi).where(
                UniversityBvi.olympiad_id == _as_uuid(olympiad_id),
                UniversityBvi.university_id == _as_uuid(university_id),
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            return False
        await session.delete(link)
        await session.commit()
        return True
