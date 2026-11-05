"""Аудит-лог и оптимистичная блокировка.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.String(), nullable=False, index=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('action', sa.String(), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('request_id', sa.String(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_audit_logs_createdAt ON audit_logs ("createdAt")')

    # Версии для оптимистичной блокировки там, где их ещё нет.
    op.add_column('olympiad_seasons', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('season_profiles', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('university_programs', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('university_programs', 'version')
    op.drop_column('season_profiles', 'version')
    op.drop_column('olympiad_seasons', 'version')
    op.drop_table('audit_logs')