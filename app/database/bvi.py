"""Слой доступа к связи «университет даёт БВИ за олимпиаду».

Связь читается в обе стороны: по университету получаем олимпиады, по
олимпиаде — университеты. Возвращаются готовые словари каталога, поэтому
страница университета и страница олимпиады строятся одинаково, а фронтенду
не нужно знать про таблицу ``university_olympiads``.

Инварианты, которые держит этот модуль:

- одна пара (университет, олимпиада) — одна связь (уникальный индекс в БД и
  обработка конфликта при параллельной вставке), поэтому «две одинаковые
  связи» невозможны даже при гонке двух запросов;
- университет **не создаёт олимпиаду**: здесь только ссылки на существующие
  записи каталога;
- новая заявка возможна только по актуальной олимпиаде (``PUBLISHED``): правило
  проверяется в ``request_bvi_link``, а не только в роутере, поэтому его нельзя
  обойти другим вызывающим; уже существующая связь возвращается как есть —
  архив сохраняет историю;
- заявка представителя (``PENDING``) не видна в публичных списках: там только
  подтверждённые администратором связи (``CONFIRMED``).
"""

import uuid as uuid_mod
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.users import ROLE_ADMIN
from app.middlewares.serializers import (
    bvi_link_to_dict,
    olympiad_to_dict,
    university_to_dict,
)
from app.models.benefit_versions import BenefitRuleVersion
from app.models.bvi import UniversityBvi
from app.models.olympiads import Olympiads
from app.models.universities import Universities

#: Допустимые виды льготы (ТЗ §4.3).
BENEFIT_TYPES = ('BVI', 'EGE_100', 'DVI_100', 'OTHER')

#: Допустимые статусы проверки связи (ТЗ §7.1).
VERIFICATION_STATUSES = ('unverified', 'verified', 'rejected')

#: Поля правила льготы, участвующие в версионировании (ТЗ §8).
BENEFIT_RULE_FIELDS = (
    'benefit_type',
    'result_requirement',
    'subject',
    'programs',
    'extra_requirements',
    'source_url',
    'valid_until',
    'status',
    'verification_status',
    'university_confirmed',
)


def _rule_snapshot(link) -> dict:
    """Снимок правила льготы для истории версий.

    Снимок уходит в JSONB, поэтому даты приводятся к ISO-строке: ``json`` не
    умеет сериализовать ``date``/``datetime`` и запись версии падала бы с
    ``TypeError``. Обратно значения превращаются в даты при откате
    (``_snapshot_value``), поэтому снимок остаётся пригодным для восстановления.
    """
    snapshot = {field: getattr(link, field) for field in BENEFIT_RULE_FIELDS}
    snapshot = {key: _snapshot_value(value) for key, value in snapshot.items()}
    snapshot['source_doc_id'] = (
        str(link.source_doc_id) if link.source_doc_id else None
    )
    snapshot['source_meta'] = link.source_meta
    return snapshot


def _snapshot_value(value):
    """Привести значение поля правила к JSON-совместимому виду."""
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _restore_value(field: str, value):
    """Вернуть полю правила тип, которого ждёт колонка.

    В снимке даты лежат строками, поэтому при откате их нужно разобрать обратно
    в ``date``/``datetime``: иначе в колонку ``DATE`` уехала бы строка.
    """
    if value is None:
        return None
    if field == 'valid_until':
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value
    if field == 'programs':
        if isinstance(value, list):
            return [str(item) for item in value]
        return value
    return value


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


async def list_links_enriched(
    *,
    status: str | None = None,
    verification_status: str | None = None,
    benefit_type: str | None = None,
    university_id=None,
    olympiad_id=None,
    subject: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Очередь модерации одним запросом, с постраничной выборкой.

    Названия университета и олимпиады подтягиваются JOIN-ом, а не отдельными
    чтениями на каждую строку: раньше на N связей уходило 2N+1 запросов, и
    очередь модерации замедлялась линейно вместе с ростом каталога.

    ``limit``/``offset`` ограничивают страницу на уровне СУБД: панель не должна
    тянуть весь каталог связей, чтобы показать первые несколько.
    """
    statement = (
        select(UniversityBvi, Universities.name, Olympiads.name, Olympiads.status)
        .join(Universities, UniversityBvi.university_id == Universities.id)
        .join(Olympiads, UniversityBvi.olympiad_id == Olympiads.id)
        .order_by(UniversityBvi.createdAt, UniversityBvi.id)
    )
    statement = _apply_link_filters(
        statement,
        status=status,
        verification_status=verification_status,
        benefit_type=benefit_type,
        university_id=university_id,
        olympiad_id=olympiad_id,
        subject=subject,
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [
            {
                **bvi_link_to_dict(link),
                'university_name': university_name,
                'olympiad_name': olympiad_name,
                'olympiad_status': olympiad_status,
            }
            for link, university_name, olympiad_name, olympiad_status in result.all()
        ]


def _apply_link_filters(
    statement,
    *,
    status: str | None = None,
    verification_status: str | None = None,
    benefit_type: str | None = None,
    university_id=None,
    olympiad_id=None,
    subject: str | None = None,
):
    """Общие фильтры связей: используются списком и подсчётом.

    Фильтры вынесены в одну функцию, чтобы ``list`` и ``count`` не разошлись:
    рассинхронизация давала бы ``total`` больше числа реально отдаваемых строк.
    """
    if status is not None:
        statement = statement.where(UniversityBvi.status == status)
    if verification_status is not None:
        statement = statement.where(
            UniversityBvi.verification_status == verification_status
        )
    if benefit_type is not None:
        statement = statement.where(UniversityBvi.benefit_type == benefit_type)
    if university_id is not None:
        statement = statement.where(
            UniversityBvi.university_id == _as_uuid(university_id)
        )
    if olympiad_id is not None:
        statement = statement.where(
            UniversityBvi.olympiad_id == _as_uuid(olympiad_id)
        )
    if subject is not None:
        statement = statement.where(UniversityBvi.subject == subject)
    return statement


async def count_links(
    *,
    status: str | None = None,
    verification_status: str | None = None,
    benefit_type: str | None = None,
    university_id=None,
    olympiad_id=None,
    subject: str | None = None,
) -> int:
    """Число связей (с учётом фильтра) — для ``total`` в постраничном ответе."""
    statement = _apply_link_filters(
        select(func.count()).select_from(UniversityBvi),
        status=status,
        verification_status=verification_status,
        benefit_type=benefit_type,
        university_id=university_id,
        olympiad_id=olympiad_id,
        subject=subject,
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


def _apply_olympiad_link_filters(
    statement,
    *,
    include_pending: bool = False,
    benefit_type: str | None = None,
    subject: str | None = None,
    verification_status: str | None = None,
):
    """Фильтры связей при чтении олимпиад/университетов через JOIN.

    ``benefit_type``/``subject``/``verification_status`` фильтруют именно связь,
    поэтому условия пишутся по ``UniversityBvi``, а не по каталогу.
    """
    if not include_pending:
        statement = statement.where(UniversityBvi.status == 'CONFIRMED')
    if benefit_type is not None:
        statement = statement.where(UniversityBvi.benefit_type == benefit_type)
    if subject is not None:
        statement = statement.where(UniversityBvi.subject == subject)
    if verification_status is not None:
        statement = statement.where(
            UniversityBvi.verification_status == verification_status
        )
    return statement


async def list_olympiads_for_university(
    university_id,
    *,
    include_pending: bool = False,
    benefit_type: str | None = None,
    subject: str | None = None,
    verification_status: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Олимпиады, дающие БВИ в университете (по умолчанию — подтверждённые).

    JOIN по ``olympiads`` отсекает связи на несуществующие олимпиады: FK
    защищает от «висячих» id после ручных правок БД. Поддерживает фильтры по
    виду льготы, предмету и статусу проверки, а также страницу (ТЗ §4.5, §10.1).
    """
    statement = (
        select(Olympiads, UniversityBvi)
        .join(UniversityBvi, UniversityBvi.olympiad_id == Olympiads.id)
        .where(UniversityBvi.university_id == _as_uuid(university_id))
        .order_by(Olympiads.name_norm, Olympiads.id)
    )
    statement = _apply_olympiad_link_filters(
        statement,
        include_pending=include_pending,
        benefit_type=benefit_type,
        subject=subject,
        verification_status=verification_status,
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [
            {
                **olympiad_to_dict(olympiad),
                # Правило льготы отдаём рядом с олимпиадой: вид льготы, предмет,
                # статус проверки и подтверждение вузом нужны карточке.
                'bvi_status': link.status,
                'benefit_type': link.benefit_type,
                'result_requirement': link.result_requirement,
                'subject': link.subject,
                'programs': link.programs,
                'extra_requirements': link.extra_requirements,
                'source_url_rule': link.source_url,
                'valid_until': link.valid_until.isoformat() if link.valid_until else None,
                'verification_status': link.verification_status,
                'university_confirmed': bool(link.university_confirmed),
                # Связь историческая, если олимпиады больше нет в актуальном
                # перечне. Саму связь не удаляем: университет действительно давал
                # БВИ, пока олимпиада была актуальной.
                'is_historical': olympiad.status != 'PUBLISHED',
            }
            for olympiad, link in result.all()
        ]


async def count_olympiads_for_university(
    university_id,
    *,
    include_pending: bool = False,
    benefit_type: str | None = None,
    subject: str | None = None,
    verification_status: str | None = None,
) -> int:
    """Число олимпиад вуза под фильтром — для ``total``."""
    statement = _apply_olympiad_link_filters(
        select(func.count())
        .select_from(UniversityBvi)
        .where(UniversityBvi.university_id == _as_uuid(university_id)),
        include_pending=include_pending,
        benefit_type=benefit_type,
        subject=subject,
        verification_status=verification_status,
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


async def list_universities_for_olympiad(
    olympiad_id,
    *,
    include_pending: bool = False,
    benefit_type: str | None = None,
    subject: str | None = None,
    verification_status: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Университеты, дающие БВИ за олимпиаду (обратная сторона связи)."""
    statement = (
        select(Universities, UniversityBvi)
        .join(UniversityBvi, UniversityBvi.university_id == Universities.id)
        .where(UniversityBvi.olympiad_id == _as_uuid(olympiad_id))
        .order_by(Universities.name_norm, Universities.id)
    )
    statement = _apply_olympiad_link_filters(
        statement,
        include_pending=include_pending,
        benefit_type=benefit_type,
        subject=subject,
        verification_status=verification_status,
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)

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
                'bvi_status': link.status,
                'benefit_type': link.benefit_type,
                'result_requirement': link.result_requirement,
                'subject': link.subject,
                'verification_status': link.verification_status,
                'university_confirmed': bool(link.university_confirmed),
                'is_historical': is_historical,
            }
            for university, link in result.all()
        ]


async def count_universities_for_olympiad(
    olympiad_id,
    *,
    include_pending: bool = False,
    benefit_type: str | None = None,
    subject: str | None = None,
    verification_status: str | None = None,
) -> int:
    """Число университетов под фильтром — для ``total``."""
    statement = _apply_olympiad_link_filters(
        select(func.count())
        .select_from(UniversityBvi)
        .where(UniversityBvi.olympiad_id == _as_uuid(olympiad_id)),
        include_pending=include_pending,
        benefit_type=benefit_type,
        subject=subject,
        verification_status=verification_status,
    )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


class BviRequestError(ValueError):
    """Заявку на связь БВИ создать нельзя.

    Доменное исключение слоя данных: правило «архивная олимпиада не получает
    новых заявок» держится здесь, а не только в HTTP-роутере. Иначе любой будущий
    вызывающий (Celery-задача, административный скрипт, второй эндпоинт) мог бы
    обойти проверку, и каталог тихо пополнялся бы связями с олимпиадами,
    которых уже нет в перечне РСОШ.

    Несёт ``status_code`` и ``detail`` — HTTP-слой подставляет их в ответ без
    собственной логики, поэтому текст ошибки не дублируется.
    """

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


#: Статус олимпиады, для которого связи БВИ ещё имеют смысл.
OLYMPIAD_ACTIVE_STATUS = 'PUBLISHED'


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

    Правила, которые держит именно эта функция (а не роутер):

    - олимпиада должна существовать (404);
    - олимпиада должна быть актуальной (``PUBLISHED``), иначе 409 — и это
      проверяется **до** идемпотентности. Иначе повторный запрос по уже
      существующей связи отвечал бы «201 Created», то есть утверждал бы, что
      заявку приняли, хотя олимпиада в архиве;
    - для актуальной олимпиады повтор возвращает существующую связь без
      изменений (идемпотентность);
    - конкурентные заявки на одну пару не приводят к 500: уникальный индекс
      остаётся последней линией защиты, а конфликт обрабатывается как
      «связь уже создана».

    Строка олимпиады читается с блокировкой: архивирование не может пройти
    между проверкой и вставкой связи.
    """
    olympiad_uuid = _as_uuid(olympiad_id)
    university_uuid = _as_uuid(university_id)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        olympiad_result = await session.execute(
            select(Olympiads.status)
            .where(Olympiads.id == olympiad_uuid)
            .with_for_update()
        )
        olympiad_status = olympiad_result.scalar_one_or_none()
        if olympiad_status is None:
            raise BviRequestError('Олимпиада не найдена', status_code=404)
        if olympiad_status != OLYMPIAD_ACTIVE_STATUS:
            raise BviRequestError(
                'Олимпиада архивирована: её нет в актуальном перечне РСОШ, '
                'новые заявки БВИ за неё не принимаются. Подтверждённые ранее '
                'связи сохраняются.',
                status_code=409,
            )

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
        try:
            await session.commit()
        except IntegrityError:
            # Гонка: пара (университет, олимпиада) уникальна, и параллельный
            # запрос успел вставить связь раньше нас. Для вызывающего это тот же
            # идемпотентный результат — «связь есть», а не ошибка сервера.
            await session.rollback()
            return await get_link(olympiad_uuid, university_uuid)
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

    Строка связи читается с блокировкой (``SELECT ... FOR UPDATE``): без неё
    параллельные ``confirm`` и ``reject`` успевали прочитать ``PENDING``
    оба, и отклонение удаляло связь уже после того, как подтверждение её
    записало — связь исчезала из каталога вместе с ``confirmedBy``. Под
    блокировкой возможен ровно один исход: либо подтверждение, либо удаление.
    """
    if action not in MODERATION_ACTIONS:
        raise ValueError(f'Unsupported BVI moderation action: {action}')

    olympiad_uuid = _as_uuid(olympiad_id)
    university_uuid = _as_uuid(university_id)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UniversityBvi)
            .where(
                UniversityBvi.olympiad_id == olympiad_uuid,
                UniversityBvi.university_id == university_uuid,
            )
            .with_for_update()
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


class BviRemoveError(ValueError):
    """Связь нельзя удалить запросившему пользователю.

    Как и ``BviRequestError``, несёт ``status_code`` и ``detail``: HTTP-слой
    подставляет их в ответ, не дублируя правило. Текст объясняет администратору
    причину, а не называет код ошибки базы.
    """

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def remove_bvi_link(
    olympiad_id,
    university_id,
    *,
    requested_by_role=None,
) -> bool:
    """Удалить связь целиком одной атомарной операцией под блокировкой строки.

    Роль запросившего передаётся сюда, а не проверяется роутером отдельным
    чтением: раньше роутер читал связь, проверял статус и удалял отдельной
    операцией, и параллельное подтверждение успевало превратить ``PENDING`` в
    ``CONFIRMED`` ровно между проверкой и удалением — подтверждённая связь
    исчезала по правилу, действующему для неподтверждённых заявок.

    Правила, проверяемые уже под блокировкой:

    - связи нет → ``False`` (роутер отвечает 404);
    - ``CONFIRMED`` удаляет только администратор, иначе ``BviRemoveError``
      (409): подтверждение администратора — публичный факт, и представитель
      не снимает его одним запросом;
    - остальное удаляется → ``True`` (``PENDING``-заявка представителем
      своего вуза либо любое состояние по решению администратора).
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            link = (
                await session.execute(
                    select(UniversityBvi)
                    .where(
                        UniversityBvi.olympiad_id == _as_uuid(olympiad_id),
                        UniversityBvi.university_id == _as_uuid(university_id),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if link is None:
                return False
            if link.status == 'CONFIRMED' and requested_by_role != ROLE_ADMIN:
                raise BviRemoveError(
                    'Связь подтверждена администратором: снять подтверждение '
                    'может только администратор'
                )
            await session.delete(link)
            return True


class BenefitRuleError(ValueError):
    """Правило нельзя изменить с переданными значениями.

    Несёт ``status_code``/``detail`` для HTTP-слоя, как и прочие ошибки этого
    модуля. Текст объясняет причину человеку, а не называет код БД.
    """

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def _record_version(
    session,
    link,
    *,
    changed_by=None,
    reason: str | None = None,
    is_rollback: bool = False,
) -> BenefitRuleVersion:
    """Записать текущее состояние правила как новую версию.

    Нумерация монотонная в пределах правила. Номер берётся как максимум + 1
    под блокировкой связи (вызывающий уже держит ``FOR UPDATE`` на ``link``),
    поэтому параллельные правки одного правила не создают две версии с одним
    номером.
    """
    next_version = (
        await session.execute(
            select(func.coalesce(func.max(BenefitRuleVersion.version), 0)).where(
                BenefitRuleVersion.link_id == link.id
            )
        )
    ).scalar_one() + 1
    version = BenefitRuleVersion(
        link_id=link.id,
        version=next_version,
        snapshot=_rule_snapshot(link),
        changed_by=_as_uuid(changed_by) if changed_by else None,
        changed_at=datetime.now(timezone.utc),
        reason=reason,
        verification_status=link.verification_status,
        source_doc_id=link.source_doc_id,
        source_meta=link.source_meta,
        is_rollback=is_rollback,
    )
    session.add(version)
    return version


async def update_benefit_rule(
    olympiad_id,
    university_id,
    *,
    updates: dict,
    changed_by=None,
    reason: str | None = None,
    admin: bool = False,
) -> dict | None:
    """Изменить правило льготы и зафиксировать версию.

    ``updates`` содержит только те поля правила, которые нужно поменять. Поля
    ``benefit_type`` и ``verification_status`` валидируются по спискам
    допустимых значений. Изменение статуса проверки ``verified`` проставляет
    ``verified_by``/``verified_at``.

    Возвращает словарь правила с добавленным ``version`` (номер только что
    записанной версии) или ``None``, если связи нет.

    Версия создаётся на каждое результативное изменение: без этого откат был бы
    невозможен, а «кто и когда поменял правило льготы» — неотвечаемым.
    """
    allowed = set(BENEFIT_RULE_FIELDS)
    unknown = set(updates) - allowed
    if unknown:
        raise BenefitRuleError(
            f'Неизвестные поля правила: {", ".join(sorted(unknown))}',
            status_code=400,
        )
    if 'benefit_type' in updates and updates['benefit_type'] not in BENEFIT_TYPES:
        raise BenefitRuleError(
            'Недопустимый вид льготы. Разрешены: ' + ', '.join(BENEFIT_TYPES) + '.',
            status_code=400,
        )
    if (
        'verification_status' in updates
        and updates['verification_status'] not in VERIFICATION_STATUSES
    ):
        raise BenefitRuleError(
            'Недопустимый статус проверки. Разрешены: '
            + ', '.join(VERIFICATION_STATUSES)
            + '.',
            status_code=400,
        )

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        link = (
            await session.execute(
                select(UniversityBvi)
                .where(
                    UniversityBvi.olympiad_id == _as_uuid(olympiad_id),
                    UniversityBvi.university_id == _as_uuid(university_id),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if link is None:
            return None

        changed = False
        for field, value in updates.items():
            if getattr(link, field) != value:
                setattr(link, field, value)
                changed = True
            elif field == 'verification_status':
                # Значение то же, но повторная проверка администратором
                # должна обновить метку времени и автора — это тоже факт.
                changed = changed or value == 'verified'

        if not changed:
            return {**bvi_link_to_dict(link), 'version': None, 'changed': False}

        if updates.get('verification_status') == 'verified' and admin and changed_by:
            link.verified_by = _as_uuid(changed_by)
            link.verified_at = now
        elif 'verification_status' in updates:
            # Снятие проверки (unverified/rejected) обнуляет и автора, и время:
            # иначе по записи было бы видно, кто «проверял» уже неверящее правило.
            link.verified_by = None
            link.verified_at = None

        link.updatedAt = now
        version = await _record_version(
            session, link, changed_by=changed_by, reason=reason
        )
        await session.commit()
        await session.refresh(link)
        return {
            **bvi_link_to_dict(link),
            'version': version.version,
            'changed': True,
        }


async def list_benefit_versions(link_id) -> list[dict]:
    """История версий правила в порядке возрастания номера."""
    from app.middlewares.serializers import benefit_version_to_dict

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BenefitRuleVersion)
            .where(BenefitRuleVersion.link_id == _as_uuid(link_id))
            .order_by(BenefitRuleVersion.version)
        )
        return [benefit_version_to_dict(row) for row in result.scalars().all()]


async def rollback_benefit_rule(
    link_id,
    version: int,
    *,
    changed_by=None,
    reason: str | None = None,
) -> dict | None:
    """Откатить правило к выбранной версии, создав новую версию.

    Промежуточные версии не удаляются: откат — это тоже изменение, и оно
    должно быть видно в истории. Новая версия помечается ``is_rollback``.
    Возвращает ``None``, если связи или указанной версии нет.
    """
    async with AsyncSessionLocal() as session:
        link = (
            await session.execute(
                select(UniversityBvi)
                .where(UniversityBvi.id == _as_uuid(link_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if link is None:
            return None
        source = (
            await session.execute(
                select(BenefitRuleVersion).where(
                    BenefitRuleVersion.link_id == link.id,
                    BenefitRuleVersion.version == version,
                )
            )
        ).scalar_one_or_none()
        if source is None:
            return None

        snapshot = source.snapshot or {}
        for field in BENEFIT_RULE_FIELDS:
            if field in snapshot:
                setattr(link, field, _restore_value(field, snapshot[field]))
        if 'source_doc_id' in snapshot and snapshot['source_doc_id']:
            link.source_doc_id = _as_uuid(snapshot['source_doc_id'])
        if 'source_meta' in snapshot:
            link.source_meta = snapshot['source_meta']
        link.updatedAt = datetime.now(timezone.utc)

        new_version = await _record_version(
            session,
            link,
            changed_by=changed_by,
            reason=reason or f'Откат к версии {version}',
            is_rollback=True,
        )
        await session.commit()
        await session.refresh(link)
        return {**bvi_link_to_dict(link), 'version': new_version.version}


async def set_university_confirmation(
    olympiad_id,
    university_id,
    confirmed: bool,
    *,
    changed_by=None,
) -> dict | None:
    """Отметить подтверждение со стороны вуза (отдельно от проверки Papaya).

    Подтверждение вуза — самостоятельная характеристика: представитель вуза
    подтверждает правило по своей стороне, администратор Papaya независимо
    ведёт ``verification_status``. Одно не заменяет другое, поэтому и
    хранится отдельным полем.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        link = (
            await session.execute(
                select(UniversityBvi)
                .where(
                    UniversityBvi.olympiad_id == _as_uuid(olympiad_id),
                    UniversityBvi.university_id == _as_uuid(university_id),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if link is None:
            return None
        link.university_confirmed = bool(confirmed)
        link.university_confirmed_at = now if confirmed else None
        link.updatedAt = now
        await _record_version(
            session, link, changed_by=changed_by,
            reason='Подтверждение вузом' if confirmed else 'Снятие подтверждения вуза',
        )
        await session.commit()
        await session.refresh(link)
        return bvi_link_to_dict(link)
