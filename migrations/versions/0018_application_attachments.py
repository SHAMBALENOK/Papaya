"""Вложения к заявкам: связь документов с запросами и заявками представителей.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-19

Пользователь может приложить подтверждающие документы (фото, скан паспорта,
справку, ссылку на профиль сотрудника) к предложке университета и к заявке
на представительство. Файлы и так лежат в ``docs`` — миграция добавляет только
связь с заявкой и тип ``ATTACHMENT``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

OLD_TYPES = (
    'RSOSH_LIST', 'UNIVERSITY_ORDER', 'OTHER', 'RSOSH_TABLE', 'RSOSH_HTML',
)
NEW_TYPES = OLD_TYPES + ('ATTACHMENT',)


def _types(values) -> str:
    quoted = ', '.join(f"'{value}'" for value in values)
    return f'type IN ({quoted})'


def upgrade() -> None:
    op.add_column(
        'docs',
        sa.Column(
            'entity_request_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        'docs',
        sa.Column(
            'representative_application_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        'fk_docs_entity_request_id',
        'docs',
        'entity_requests',
        ['entity_request_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_docs_representative_application_id',
        'docs',
        'representative_applications',
        ['representative_application_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_docs_entity_request_id '
        'ON docs (entity_request_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_docs_representative_application_id '
        'ON docs (representative_application_id)'
    )

    op.execute('ALTER TABLE docs DROP CONSTRAINT IF EXISTS ck_docs_type')
    op.execute(
        f'ALTER TABLE docs ADD CONSTRAINT ck_docs_type CHECK ({_types(NEW_TYPES)})'
    )


def downgrade() -> None:
    op.execute("DELETE FROM docs WHERE type = 'ATTACHMENT'")
    op.execute('ALTER TABLE docs DROP CONSTRAINT IF EXISTS ck_docs_type')
    op.execute(
        f'ALTER TABLE docs ADD CONSTRAINT ck_docs_type CHECK ({_types(OLD_TYPES)})'
    )
    op.execute('DROP INDEX IF EXISTS ix_docs_representative_application_id')
    op.execute('DROP INDEX IF EXISTS ix_docs_entity_request_id')
    op.drop_constraint(
        'fk_docs_representative_application_id', 'docs', type_='foreignkey'
    )
    op.drop_constraint('fk_docs_entity_request_id', 'docs', type_='foreignkey')
    op.drop_column('docs', 'representative_application_id')
    op.drop_column('docs', 'entity_request_id')
