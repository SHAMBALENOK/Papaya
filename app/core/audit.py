"""Аудит административных действий.

Каждое изменение прав или состояния пользователя фиксируется отдельной строкой
лога в формате ``ключ=значение``: кто (``actor``), над кем (``target``), что
изменилось (``old_role`` → ``new_role``), когда (timestamp записи), в рамках
какого запроса (``request_id``) и с какого адреса (``ip``).

Отдельный логгер ``papaya.audit`` вместо обычного ``papaya.admin`` нужен,
чтобы аудит можно было выводить/хранить независимо от операционных логов:
именно он отвечает на вопрос «кто выдал администратора и когда». Формат
намеренно машиночитаемый — строку легко разобрать и загрузить в SIEM.
"""

import logging

from app.middlewares.request_id import current_request_id

logger = logging.getLogger('papaya.audit')


def log_admin_action(
    action: str,
    *,
    actor_id,
    target_id=None,
    ip: str | None = None,
    **fields,
) -> None:
    """Записать административное действие одной строкой аудита."""
    extras = ' '.join(f'{key}={value}' for key, value in sorted(fields.items()))
    logger.info(
        'admin.%s request_id=%s actor=%s target=%s ip=%s%s',
        action,
        current_request_id(),
        actor_id,
        target_id,
        ip or '-',
        f' {extras}' if extras else '',
    )


def log_role_change(
    *,
    actor_id,
    target_id,
    old_role,
    new_role,
    university_id=None,
    ip: str | None = None,
) -> None:
    """Отдельный, более наглядный случай — смена роли пользователя."""
    log_admin_action(
        'role_change',
        actor_id=actor_id,
        target_id=target_id,
        ip=ip,
        old_role=old_role,
        new_role=new_role,
        university_id=university_id if university_id is not None else 'none',
    )
