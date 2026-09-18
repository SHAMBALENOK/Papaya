"""Align legacy users timestamps to timezone-aware.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17

Часть баз снабжения унаследована от ``Base.metadata.create_all``, где
``users.createdAt``/``users.updatedAt`` фактически были TIMESTAMP WITHOUT TIME
ZONE (модель декларировала ``DateTime(timezone=True)``, но asyncpg писал naive
значения). В колонках ``events`` время timezone-aware, поэтому контракт данных
расходится. Миграция приводит users к общему знаменателю: ``WITH TIME ZONE``.
"""

import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Сделать колонки времени users timezone-aware."""
    op.alter_column(
        'users',
        'createdAt',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(timezone=False),
        postgresql_using='"createdAt"::timestamp with time zone',
    )
    op.alter_column(
        'users',
        'updatedAt',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(timezone=False),
        postgresql_using='"updatedAt"::timestamp with time zone',
    )


def downgrade() -> None:
    """Вернуть naive-колонки (теряя смещение времени в данных)."""
    op.alter_column(
        'users',
        'createdAt',
        type_=sa.DateTime(timezone=False),
        existing_type=sa.DateTime(timezone=True),
    )
    op.alter_column(
        'users',
        'updatedAt',
        type_=sa.DateTime(timezone=False),
        existing_type=sa.DateTime(timezone=True),
    )