"""Удаление исторической таблицы events.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26

Данные событий уже перенесены в каталог олимпиад миграцией 0004, поэтому
старая таблица больше не нужна: «событие» — это прошлая концепция проекта,
а каталог олимпиад — текущая.

Удаление отдельной миграцией (а не в 0004) сделано специально: между 0004 и
0005 перенос данных уже произошёл, поэтому откат (downgrade) каждой миграции
возвращает согласованное состояние — 0004 откатывается в базу, где таблица
``events`` ещё существует.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('events')


def downgrade() -> None:
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('disc', sa.String(), nullable=True),
        sa.Column('preview_picture', sa.String(), nullable=True),
        sa.Column('picture', sa.String(), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_events_owner ON events (owner)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_events_createdAt ON events ("createdAt")')

    # Вернуть олимпиады в события: обратная операция к миграции 0004.
    op.execute(
        """
        INSERT INTO events (
            id, name, disc, picture, preview_picture, "isActive",
            "createdAt", "updatedAt"
        )
        SELECT
            o.id,
            o.name,
            o.description,
            o.image,
            o.image,
            o.status = 'PUBLISHED',
            o."createdAt",
            o."updatedAt"
        FROM olympiads o
        ON CONFLICT DO NOTHING
        """
    )
