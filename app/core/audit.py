"""Аудит административных действий.

Каждое критическое действие фиксируется двумя способами:

- строкой лога ``papaya.audit`` в формате ``ключ=значение`` (кто, над кем,
  что изменилось, в рамках какого запроса и с какого адреса) — её легко
  разобрать и загрузить в SIEM;
- записью в таблицу ``audit_events`` (``database.audit.record_event``) —
  лог ротируется, а ответ на вопрос «кто выдал администратора / проверил
  правило / подтвердил импорт и когда» нужен спустя месяцы.

Сбой записи в БД не ломает действие: он логируется, и действие завершается.
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
    """Записать административное действие одной строкой лога аудита."""
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


async def audit(
    action: str,
    *,
    actor_id,
    target_type: str | None = None,
    target_id=None,
    ip: str | None = None,
    **details,
) -> None:
    """Строка лога + персистентная запись события (ТЗ §10)."""
    log_admin_action(action, actor_id=actor_id, target_id=target_id, ip=ip, **details)
    from app.database import audit as audit_db

    await audit_db.record_event(
        action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        details=details or None,
        ip=ip,
        request_id=current_request_id(),
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
    """Отдельный, более наглядный случай — смена роли пользователя (лог)."""
    log_admin_action(
        'role_change',
        actor_id=actor_id,
        target_id=target_id,
        ip=ip,
        old_role=old_role,
        new_role=new_role,
        university_id=university_id if university_id is not None else 'none',
    )


async def audit_role_change(
    *,
    actor_id,
    target_id,
    old_role,
    new_role,
    university_id=None,
    ip: str | None = None,
) -> None:
    """Смена роли: лог + запись в журнал."""
    await audit(
        'role_change',
        actor_id=actor_id,
        target_type='user',
        target_id=target_id,
        ip=ip,
        old_role=old_role,
        new_role=new_role,
        university_id=str(university_id) if university_id is not None else None,
    )
