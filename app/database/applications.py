"""Слой доступа к заявкам на роль представителя вуза (ТЗ §3.4).

Поток: пользователь подаёт заявку (``PENDING``) → администратор одобряет
(``APPROVED``, пользователь получает роль ``EDITOR`` с привязкой к вузу) или
отклоняет (``REJECTED`` с причиной).

Одобрение выдаёт роль через тот же защищённый путь, что и ручное назначение
(``database.users.apply_role_guarded``): второго способа стать представителем
не появляется. Активная заявка на пару (пользователь, вуз) может быть только
одна (уникальный частичный индекс в БД).
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database import users as users_db
from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import application_to_dict
from app.models.applications import RepresentativeApplication
from app.models.users import Users
from app.models.universities import Universities

APPLICATION_PENDING = 'PENDING'
APPLICATION_APPROVED = 'APPROVED'
APPLICATION_REJECTED = 'REJECTED'

APPLICATION_STATUSES = (
    APPLICATION_PENDING,
    APPLICATION_APPROVED,
    APPLICATION_REJECTED,
)


def _as_uuid(value) -> uuid_mod.UUID:
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def submit_application(
    user_id,
    university_id,
    *,
    motivation: str | None = None,
) -> dict | None:
    """Подать заявку на роль представителя.

    Возвращает ``None``, если активная заявка на эту пару уже есть (закрывает
    и явный повтор, и гонку двух параллельных подач).
    """
    application = RepresentativeApplication(
        user_id=_as_uuid(user_id),
        university_id=_as_uuid(university_id),
        motivation=motivation,
        status=APPLICATION_PENDING,
    )
    async with AsyncSessionLocal() as session:
        session.add(application)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(application)
        return application_to_dict(application)


async def list_applications(
    *,
    status: str | None = None,
    user_id=None,
    university_id=None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Заявки с фильтрами (очередь администратора / свои заявки пользователя).

    К заявке подтягиваются имя заявителя и название вуза: администратор
    принимает решение о человеке и вузе, и по одному идентификатору решать
    не по чему.
    """
    statement = (
        select(
            RepresentativeApplication,
            Users.name,
            Users.surname,
            Users.email,
            Universities.name,
            Universities.short_name,
        )
        .outerjoin(Users, RepresentativeApplication.user_id == Users.id)
        .outerjoin(
            Universities, RepresentativeApplication.university_id == Universities.id
        )
    )
    if status is not None:
        statement = statement.where(RepresentativeApplication.status == status)
    if user_id is not None:
        statement = statement.where(
            RepresentativeApplication.user_id == _as_uuid(user_id)
        )
    if university_id is not None:
        statement = statement.where(
            RepresentativeApplication.university_id == _as_uuid(university_id)
        )
    statement = statement.order_by(
        RepresentativeApplication.createdAt.desc(),
        RepresentativeApplication.id,
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [
            {
                **application_to_dict(item),
                'applicant_name': ' '.join(
                    part for part in (user_name, user_surname) if part
                )
                or None,
                'applicant_email': applicant_email,
                'university_name': university_name,
                'university_short_name': university_short_name,
            }
            for (
                item,
                user_name,
                user_surname,
                applicant_email,
                university_name,
                university_short_name,
            ) in result.all()
        ]

async def count_applications(
    *,
    status: str | None = None,
    user_id=None,
    university_id=None,
) -> int:
    """Число заявок под фильтром — для ``total`` в постраничном ответе."""
    statement = select(func.count()).select_from(RepresentativeApplication)
    if status is not None:
        statement = statement.where(RepresentativeApplication.status == status)
    if user_id is not None:
        statement = statement.where(
            RepresentativeApplication.user_id == _as_uuid(user_id)
        )
    if university_id is not None:
        statement = statement.where(
            RepresentativeApplication.university_id == _as_uuid(university_id)
        )
    async with AsyncSessionLocal() as session:
        return (await session.execute(statement)).scalar_one()


async def get_application(application_id) -> dict | None:
    async with AsyncSessionLocal() as session:
        application = (
            await session.execute(
                select(RepresentativeApplication).where(
                    RepresentativeApplication.id == _as_uuid(application_id)
                )
            )
        ).scalar_one_or_none()
        return application_to_dict(application) if application else None


class ApplicationError(ValueError):
    """Заявку нельзя рассмотреть в её текущем состоянии."""

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def review_application(
    application_id,
    decision: str,
    *,
    reviewer_id,
    note: str | None = None,
) -> dict | str | None:
    """Одобрить или отклонить заявку.

    Одобрение выдаёт роль ``EDITOR`` с привязкой к вузу заявки. Если роль выдать
    нельзя (например, пользователь — последний активный администратор и
    понижается), возвращается строка-причина отказа из ``apply_role_guarded``.

    Назначение роли и запись о решении — одна транзакция. Иначе заявка могла бы
    остаться одобренной без представителя: статус ``APPROVED`` повторно не
    изменить, и роль пришлось бы выдавать вручную.

    Возвращает: словарь заявки; строку-причину отказа роли; ``None``, если
    заявки нет; ``ApplicationError``, если заявка уже рассмотрена.
    """
    if decision not in (APPLICATION_APPROVED, APPLICATION_REJECTED):
        raise ApplicationError('Неизвестное решение по заявке', status_code=400)

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        application = (
            await session.execute(
                select(RepresentativeApplication)
                .where(RepresentativeApplication.id == _as_uuid(application_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if application is None:
            return None
        if application.status != APPLICATION_PENDING:
            raise ApplicationError(
                'Заявка уже рассмотрена: повторное решение невозможно.'
            )

        try:
            if decision == APPLICATION_APPROVED:
                role_outcome = await users_db.apply_role_guarded(
                    str(application.user_id),
                    users_db.ROLE_UNIVERSITY_REP,
                    str(application.university_id),
                    session=session,
                )
                if isinstance(role_outcome, str):
                    # Роль выдать нельзя: заявка остаётся в ожидании, чтобы
                    # администратор мог вернуться к ней позже, а не «одобрить»
                    # заявку, по которой представителя так и не будет.
                    await session.rollback()
                    return role_outcome

            application.status = decision
            application.reviewed_by = _as_uuid(reviewer_id)
            application.reviewed_at = now
            application.decision_note = note
            application.updatedAt = now
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ApplicationError(
                'Не удалось сохранить решение по заявке',
                status_code=409,
            ) from exc
        await session.refresh(application)
        return application_to_dict(application)
