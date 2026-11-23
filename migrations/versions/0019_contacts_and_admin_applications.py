"""Контакты представителей и заявки на администратора.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-20

Две независимые вещи, объединённые одним продуктовым сценарием — доверием к
человеку по ту сторону заявки:

* ``representative_applications.contact_email`` — почта для связи с
  кандидатом, чтобы администратор не искал её в профиле;
* ``admin_applications`` — отдельная очередь заявок на роль администратора.
  Она не смешивается с ``entity_requests``: одобрение здесь выдаёт роль, а не
  создаёт сущность каталога.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'representative_applications',
        sa.Column('contact_email', sa.String(), nullable=True),
    )

    op.create_table(
        'admin_applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_email', sa.String(), nullable=False),
        sa.Column('motivation', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column(
            'createdAt', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updatedAt', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name='fk_admin_applications_user_id', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['reviewed_by'], ['users.id'],
            name='fk_admin_applications_reviewed_by', ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name='ck_admin_applications_status',
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_admin_applications_user_id '
        'ON admin_applications (user_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_admin_applications_status '
        'ON admin_applications (status)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_admin_applications_createdAt '
        'ON admin_applications ("createdAt")'
    )
    # Одна открытая заявка на пользователя: повторная отправка возвращает
    # существующую, а гонка двух запросов не создаёт дубль.
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_applications_pending_user '
        "ON admin_applications (user_id) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS uq_admin_applications_pending_user')
    op.drop_table('admin_applications')
    op.drop_column('representative_applications', 'contact_email')
