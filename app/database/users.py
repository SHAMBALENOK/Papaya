import uuid as uuid_mod
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import user_to_dict
from app.models.users import Users

# Роли платформы. Константы живут в слое доступа: от них зависят и проверки
# прав (app/core/deps.py), и правила назначения роли (apply_role ниже).
ROLE_USER = 'USER'
ROLE_UNIVERSITY_REP = 'EDITOR'
ROLE_ADMIN = 'ADMIN'
ROLES = (ROLE_USER, ROLE_UNIVERSITY_REP, ROLE_ADMIN)


class RoleInvariantError(ValueError):
    """Нарушение инварианта роли представителя университета.

    Несёт понятный текст: его отдаёт HTTP-слой как 400, поэтому сообщение
    должно быть пригодно для показа администратору.
    """


def _as_uuid(value):
    """Привести id пользователя к UUID (пути маршрутов дают строки)."""
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _full_user_dict(user) -> dict:
    """Сериализовать пользователя вместе с хэшем пароля для входа."""
    data = user_to_dict(user)
    data['password'] = user.password
    return data


async def add_user(ins: dict):
    """Создать пользователя в базе данных.

    Возвращает ``None``, если такой email уже существует (закрывает гонку
    двух одновременных регистраций: между SELECT и INSERT мог появиться второй
    пользователь с тем же адресом).
    """
    salt = bcrypt.gensalt(rounds=12)
    user = Users(
        name=ins.get('name'),
        surname=ins.get('surname'),
        email=ins.get('email'),
        password=bcrypt.hashpw(
            ins.get('password').encode('utf-8'),
            salt,
        ).decode('utf-8'),
    )
    async with AsyncSessionLocal() as session:
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(user)
        return user_to_dict(user)


async def find_user_by_email(email: str):
    """Найти пользователя по email (включая хэш пароля)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.email == email)
        )
        user = result.scalars().first()
        return _full_user_dict(user) if user else None


async def find_user_by_id(user_id: str):
    """Найти пользователя по id без выдачи хэша пароля."""
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()
        return user_to_dict(user) if user else None


# Поля, которые разрешено менять через edit_user. Пароль сознательно не входит:
# смена пароля должна проходить отдельный путь с хешированием, а не setattr.
# id, createdAt и updatedAt задаёт сервер.
_USER_EDITABLE_FIELDS = frozenset({
    'name', 'surname', 'email', 'gender', 'bday', 'bio', 'phone',
    'country', 'region', 'status', 'role', 'isActive', 'university_id',
})


async def edit_user(user_id: str, ins: dict):
    """Изменить данные пользователя.

    Применяются только поля из allowlist ``_USER_EDITABLE_FIELDS``; остальное
    игнорируется. ``updatedAt`` перезаписывается сервером.
    """
    if isinstance(user_id, str):
        user_id = uuid_mod.UUID(user_id)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalars().first()
        if not user:
            return None
        for key, value in ins.items():
            if key in _USER_EDITABLE_FIELDS:
                setattr(user, key, value)
        user.updatedAt = now
        try:
            await session.commit()
        except IntegrityError:
            # Email-unique конфликт (гонка двух одновременных обновлений).
            # Транзакция после исключения не должна оставаться «сломанной»:
            # явный rollback, затем пробрасываем наверх для HTTP 409.
            await session.rollback()
            raise
        await session.refresh(user)
        return user_to_dict(user)


#: Причины отказа при смене роли или активности администратора.
#:
#: Успешные операции возвращают обновлённого пользователя, поэтому отдельного
#: значения «успех» здесь нет: строка означает именно «ничего не изменили».
ADMIN_GUARD_MISSING = 'missing'
ADMIN_GUARD_LAST_ADMIN = 'last_admin'


async def _lock_admins(session) -> None:
    """Заблокировать строки всех администраторов в фиксированном порядке.

    Зачем это вместо «посчитать, потом изменить»: две параллельные
    административные операции (два администратора понижают друг друга или себя)
    видели бы одну и ту же картину и обе решили бы, что понижаемый не последний.
    В итоге система осталась бы без единого активного администратора.

    ``SELECT ... FOR UPDATE`` по всем строкам с ролью ``ADMIN`` в порядке ``id``
    сериализует такие операции: вторая ждёт первую, а после её коммита
    пересчитывает активных уже по свежему состоянию (``READ COMMITTED`` берёт
    новый снимок на каждый оператор). Порядок ``ORDER BY id`` фиксирован, поэтому
    взаимного ожидания (дедлока) не возникает.
    """
    await session.execute(
        select(Users.id)
        .where(Users.role == ROLE_ADMIN)
        .order_by(Users.id)
        .with_for_update()
    )


async def _active_admins_excluding(session, user_uuid) -> int:
    """Сколько активных администраторов останется, если убрать ``user_uuid``."""
    result = await session.execute(
        select(func.count())
        .select_from(Users)
        .where(
            Users.role == ROLE_ADMIN,
            Users.isActive.is_(True),
            Users.id != user_uuid,
        )
    )
    return result.scalar()


async def set_active_guarded(user_id, is_active: bool) -> dict | str:
    """Сменить активность пользователя, не оставив систему без администратора.

    Блокировка последнего активного администратора отклоняется: заблокированный
    администратор не может войти, а назначать новых должен действующий. Проверка
    и запись — в одной транзакции под блокировкой строк администраторов.

    Возвращает обновлённого пользователя либо строку-причину отказа:
    ``'missing'`` или ``'last_admin'``.
    """
    user_uuid = _as_uuid(user_id)

    async with AsyncSessionLocal() as session:
        await _lock_admins(session)
        current = await session.execute(
            select(Users.role, Users.isActive, Users).where(Users.id == user_uuid)
        )
        row = current.one_or_none()
        if not row:
            await session.rollback()
            return ADMIN_GUARD_MISSING

        role, is_active_now, user = row
        if role == ROLE_ADMIN and is_active_now and not is_active:
            if await _active_admins_excluding(session, user_uuid) == 0:
                # Отказ фиксируем откатом и уходим уже после закрытия сессии:
                # возврат изнутри `async with` оставляет соединение в пуле в
                # момент, когда транзакция ещё не отпустила блокировки строк.
                await session.rollback()
                return ADMIN_GUARD_LAST_ADMIN

        user.isActive = is_active
        user.updatedAt = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(user)
        return user_to_dict(user)


async def apply_role_guarded(
    user_id: str,
    role: str,
    university_id: str | None = None,
) -> dict | str:
    """Назначить роль, не понизив последнего активного администратора.

    Инварианты роли проверяются как обычно (см. ``apply_role``), а запрет на
    понижение последнего администратора проверяется под блокировкой строк
    администраторов, поэтому две параллельные операции не могут пройти обе.

    Возвращает обновлённого пользователя либо строку-причину отказа:
    ``'missing'`` или ``'last_admin'``.
    """
    if role not in ROLES:
        raise RoleInvariantError(f'Unknown role: {role}')
    if role == ROLE_UNIVERSITY_REP and not university_id:
        raise RoleInvariantError(
            'Представитель университета должен быть привязан к университету'
        )
    if role == ROLE_USER and university_id:
        raise RoleInvariantError(
            'Роль USER не предполагает привязки к университету'
        )

    user_uuid = _as_uuid(user_id)
    university_uuid = (
        uuid_mod.UUID(str(university_id)) if university_id else None
    )

    async with AsyncSessionLocal() as session:
        await _lock_admins(session)
        current = await session.execute(
            select(Users.role, Users.isActive).where(Users.id == user_uuid)
        )
        row = current.one_or_none()
        if not row:
            await session.rollback()
            return ADMIN_GUARD_MISSING

        current_role, is_active_now = row
        if role != ROLE_ADMIN and current_role == ROLE_ADMIN and is_active_now:
            if await _active_admins_excluding(session, user_uuid) == 0:
                await session.rollback()
                return ADMIN_GUARD_LAST_ADMIN

        user = (
            await session.execute(select(Users).where(Users.id == user_uuid))
        ).scalar_one_or_none()
        user.role = role
        user.university_id = university_uuid
        user.updatedAt = datetime.now(timezone.utc)
        try:
            await session.commit()
        except IntegrityError:
            # CHECK-ограничение БД: страховка от гонки и прямых правок данных.
            await session.rollback()
            raise
        await session.refresh(user)
        return user_to_dict(user)


def demote_role(user: dict) -> str:
    """Роль, которая должна остаться после снятия ADMIN.

    Если пользователь привязан к университету, он продолжает быть его
    представителем (``EDITOR``), иначе становится обычным пользователем
    (``USER``). Так смена роли не оставляет противоречий: представитель не
    может остаться без университета, а «просто пользователь» не получает
    привязку, на которую он не подписан.
    """
    return ROLE_UNIVERSITY_REP if user.get('university_id') else ROLE_USER


async def list_users(
    *,
    include_inactive: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """Вернуть пользователей для публичного или административного списка."""
    statement = select(Users)
    if not include_inactive:
        statement = statement.where(Users.isActive.is_(True))
    statement = statement.order_by(Users.createdAt.desc(), Users.id)
    if limit is not None:
        statement = statement.limit(limit)

    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [user_to_dict(user) for user in result.scalars().all()]


async def get_amount_of_users() -> int:
    """Количество пользователей в платформе."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Users)
        )
        return result.scalar()


# Счёт активных администраторов намеренно не вынесен в отдельную функцию:
# «посчитать, потом изменить» — гонка, из-за которой система могла остаться без
# администратора. Проверка живёт внутри ``set_active_guarded`` и
# ``apply_role_guarded`` под блокировкой строк администраторов.

