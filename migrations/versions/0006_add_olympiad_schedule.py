"""Add the olympiad schedule JSONB column.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24

Фаза 2 «Этапы и даты» хранит временную структуру олимпиады внутри самой
сущности ``olympiads`` — отдельная таблица stages не создаётся. Колонка
``schedule`` (JSONB) содержит источник данных о расписании::

    {
      "season": "2026/27",
      "stages": [
        {"id": "registration", "name": "Регистрация", "type": "REGISTRATION",
         "start_at": "2026-09-01T00:00:00+03:00", "end_at": "...", "timezone": "Europe/Moscow"},
        ...
      ]
    }

Вычисляемые поля (статус этапа/олимпиады, ближайший дедлайн) в БД не хранятся —
они считаются динамически при выдаче (app/core/schedule.py) и не кэшируются.
``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` делает миграцию идемпотентной как
для чистых, так и для существующих баз (старые олимпиады получают NULL).
"""

from alembic import op
from sqlalchemy.dialects import postgresql

# Названия миграции (идентификаторы ревизий)
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавить JSONB-колонку schedule (без изменения существующих данных)."""
    op.execute(
        'ALTER TABLE olympiads ADD COLUMN IF NOT EXISTS schedule JSONB'
    )


def downgrade() -> None:
    """Убрать колонку schedule."""
    op.execute('ALTER TABLE olympiads DROP COLUMN IF EXISTS schedule')