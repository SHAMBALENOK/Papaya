"""Add Organizations / Olympiads / Docs and align Users.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23

Переход к целевой доменной модели Papaya:

- ``organizations`` — источник истины об организациях (тип из
  UNIVERSITY / ORGANIZER / SCHOOL / OTHER);
- ``olympiads`` — центральный каталог; данных исторических ``events``
  переносятся в олимпиады (оригинал остаётся в ``olympiads.metadata.legacy``,
  таблица ``events`` сохраняется для отката и удаляется отдельным этапом
  очистки);
- ``docs`` — документы-источники (в т.ч. техническое состояние RSOSH-импорта);
- ``users`` получают ``organization_id`` (максимум одна организация) и
  ``metadata`` (JSONB).

Роли: исторический ``EDITOR`` → ``ORGANIZATION_ADMIN`` (удаляется вне этой
миграции, а здесь транзитивно конвертируется).

Миграция безопасна для повторного применения на уже переведённых базах:
``CREATE TABLE IF NOT EXISTS`` / ``ADD COLUMN IF NOT EXISTS`` и
``ON CONFLICT DO NOTHING`` при переносе событий.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Названия миграции (идентификаторы ревизий)
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def _name_norm_sql(column: str) -> str:
    """Нормализованное имя для точного поиска дубликатов (lower + слитые пробелы)."""
    return (
        f"lower(trim(concat(regexp_replace({column}, '\\s+', ' ', 'g'), '')))"
    )


def upgrade() -> None:
    """Создать новые таблицы, перенести события и выровнять роли."""
    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('short_name', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=False, server_default='OTHER'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('logo', sa.String(), nullable=True),
        sa.Column('contacts', postgresql.JSONB(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'olympiads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('organizer_ids', postgresql.JSONB(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('subjects', postgresql.JSONB(), nullable=False),
        sa.Column('levels', postgresql.JSONB(), nullable=False),
        sa.Column('years', postgresql.JSONB(), nullable=False),
        sa.Column('profiles', postgresql.JSONB(), nullable=False),
        sa.Column('bvi_organizations', postgresql.JSONB(), nullable=False),
        sa.Column('registration_url', sa.String(), nullable=True),
        sa.Column('official_url', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='PUBLISHED'),
        sa.Column('name_norm', sa.String(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_olympiads_name_norm ON olympiads (name_norm)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_olympiads_created_at '
        'ON olympiads ("created_at")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_organizations_created_at '
        'ON organizations ("created_at")'
    )

    op.create_table(
        'docs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False, server_default='OTHER'),
        sa.Column('storage_key', sa.String(), nullable=True),
        sa.Column('mime_type', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('olympiad_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('checksum', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='UPLOADED'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_docs_created_at ON docs ("created_at")'
    )

    # --- Users: одна организация + гибкий metadata ----------------------
    op.execute(
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id UUID'
    )
    op.execute(
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS metadata JSONB'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_users_organization_id '
        'ON users (organization_id)'
    )

    # --- Роли: EDITOR -> ORGANIZATION_ADMIN -------------------------------
    op.execute(
        "UPDATE users SET role = 'ORGANIZATION_ADMIN' WHERE role = 'EDITOR'"
    )

    # --- Перенос исторических событий в олимпиады -------------------------
    conn = op.get_bind()
    has_events = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'events')"
        )
    ).scalar()
    if not has_events:
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO olympiads (
                id, name, description, organizer_ids, subjects, levels, years,
                profiles, bvi_organizations, registration_url, official_url,
                status, name_norm, metadata, created_at, updated_at
            )
            SELECT
                e.id,
                e.name,
                e.disc,
                '[]'::jsonb,
                '[]'::jsonb,
                '[]'::jsonb,
                '[]'::jsonb,
                '[]'::jsonb,
                '[]'::jsonb,
                NULL,
                NULL,
                CASE WHEN e."isActive" = false THEN 'ARCHIVED' ELSE 'PUBLISHED' END,
                """ + _name_norm_sql('e.name') + """,
                jsonb_build_object(
                    'legacy',
                    jsonb_build_object(
                        'owner', e.owner,
                        'preview_picture', e."preview_picture",
                        'picture', e.picture,
                        'source', 'events'
                    )
                ),
                e."createdAt",
                e."updatedAt"
            FROM events e
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    """Откатить изменения: удалить новые таблицы и вернуть прежние значения."""
    op.execute("DROP TABLE IF EXISTS docs")
    op.execute("DROP TABLE IF EXISTS olympiads")
    op.execute("DROP TABLE IF EXISTS organizations")
    op.execute("DROP INDEX IF EXISTS ix_users_organization_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS organization_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS metadata")
    op.execute(
        "UPDATE users SET role = 'EDITOR' WHERE role = 'ORGANIZATION_ADMIN'"
    )