"""Инвариант роли представителя университета.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27

Представитель университета — это роль ``EDITOR``, и она бессмысленна без
привязки к конкретному вузу: непонятно, чьи связи БВИ такой человек будет
вести. Раньше состояние ``role = 'EDITOR'`` и ``university_id = NULL`` было
возможным (и им могли пользоваться), поэтому миграция:

1. приводит существующие строки к корректному виду — ``EDITOR`` без вуза
   становится обычным пользователем (роль исправления выбрана в пользу
   безопасного состояния: доступ не выдаём, данные не теряем);
2. добавляет CHECK-ограничение, запрещающее такое состояние на уровне БД,
   чтобы его нельзя было создать ни через API, ни прямым SQL-запросом.

Роли ``USER`` и ``ADMIN`` ограничением не затронуты: привязка к университету
для них допустима (у администратора она нужна, чтобы понижение вернуло роль
представителя, а не голого пользователя).
"""

from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'USER', university_id = NULL
        WHERE role = 'EDITOR' AND university_id IS NULL
        """
    )
    op.execute(
        'ALTER TABLE users ADD CONSTRAINT ck_users_representative_needs_university '
        "CHECK (role <> 'EDITOR' OR university_id IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_representative_needs_university'
    )
