"""Initial schema: users and events tables.

Revision ID: 0001
Revises:
Create Date: 2026-09-17

Базовые таблицы текущей модели данных (Users, Events). Индексы вынесены в
отдельную миграцию 0002, чтобы существующие базы, созданные через
Base.metadata.create_all, можно было сначала «заклеймить» на revision 0001,
а затем применить 0002 и получить недостающие индексы без пересоздания схемы.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Названия миграции (идентификаторы ревизий)
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать таблицы users и events."""
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('surname', sa.String(), nullable=False),
        sa.Column('gender', sa.String(), nullable=True),
        sa.Column('bday', sa.String(), nullable=True),
        sa.Column('bio', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.Column('updatedAt', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )

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


def downgrade() -> None:
    """Удалить таблицы в обратном порядке."""
    op.drop_table('events')
    op.drop_table('users')