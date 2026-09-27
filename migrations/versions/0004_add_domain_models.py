"""Доменная модель Papaya: университеты, олимпиады, БВИ, документы.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26

Переводит проект с исторической сущности ``events`` на модель, вокруг которой
построен сервис:

    University ──(university_olympiads)── Olympiad ──(source_doc_id)── Docs

Что делает миграция:

1. Создаёт ``docs``, ``olympiads``, ``universities``, ``university_olympiads``
   и колонку ``users.university_id``.
2. Переносит данные старой таблицы ``events`` в ``olympiads``
   (``name`` → ``name``, ``disc`` → ``description``, ``picture`` /
   ``preview_picture`` → ``image``, ``isActive`` → ``status``). Старую таблицу
   удаляет отдельная миграция 0005, поэтому на этом шаге данные ещё целы.
3. Добавляет индексы каталогов и ограничение уникальности пары
   «университет + олимпиада» (дубли БВИ невозможны на уровне БД).

Олимпиада здесь единая сущность каталога: записи «олимпиада 2026/2027» не
создаются, год остаётся частью названия или описания.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'docs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False, server_default='RSOSH_LIST'),
        sa.Column('storage_key', sa.String(), nullable=True),
        sa.Column('mime_type', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('checksum', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='UPLOADED'),
        sa.Column('processedAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_docs_createdAt ON docs ("createdAt")')
    op.execute('CREATE INDEX IF NOT EXISTS ix_docs_type ON docs (type)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_docs_status ON docs (status)')

    op.create_table(
        'olympiads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('name_norm', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('official_url', sa.String(), nullable=True),
        sa.Column('image', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column(
            'source_doc_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('docs.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('status', sa.String(), nullable=False, server_default='PUBLISHED'),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('name_norm', name='uq_olympiads_name_norm'),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_olympiads_createdAt ON olympiads ("createdAt")')
    op.execute('CREATE INDEX IF NOT EXISTS ix_olympiads_name_norm ON olympiads (name_norm)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_olympiads_status ON olympiads (status)')

    op.create_table(
        'universities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('name_norm', sa.String(), nullable=False),
        sa.Column('short_name', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('image', sa.String(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('name_norm', name='uq_universities_name_norm'),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_universities_name_norm ON universities (name_norm)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_universities_createdAt ON universities ("createdAt")')

    op.create_table(
        'university_olympiads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'university_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('universities.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'olympiad_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('olympiads.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column(
            'createdBy',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'confirmedBy',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            'university_id',
            'olympiad_id',
            name='uq_university_olympiads_pair',
        ),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_university_olympiads_university_id ON university_olympiads (university_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_university_olympiads_olympiad_id ON university_olympiads (olympiad_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_university_olympiads_status ON university_olympiads (status)')

    op.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS university_id uuid')
    op.execute('CREATE INDEX IF NOT EXISTS ix_users_university_id ON users (university_id)')
    op.execute(
        'DO $$ BEGIN '
        'ALTER TABLE users ADD CONSTRAINT fk_users_university_id '
        'FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE SET NULL; '
        'EXCEPTION WHEN duplicate_object THEN NULL; END $$'
    )

    # Перенос исторических событий в каталог олимпиад. name_norm считается
    # простой функцией в SQL, чтобы миграция не зависела от кода приложения.
    op.execute(
        """
        INSERT INTO olympiads (
            id, name, name_norm, description, image, status,
            "createdAt", "updatedAt"
        )
        SELECT
            e.id,
            e.name,
            lower(regexp_replace(trim(coalesce(e.name, '')), '\\s+', ' ', 'g')),
            e.disc,
            coalesce(e.picture, e.preview_picture),
            CASE WHEN coalesce(e."isActive", true) THEN 'PUBLISHED' ELSE 'ARCHIVED' END,
            e."createdAt",
            e."updatedAt"
        FROM events e
        WHERE coalesce(trim(e.name), '') <> ''
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_university_id')
    op.execute('DROP INDEX IF EXISTS ix_users_university_id')
    op.execute('ALTER TABLE users DROP COLUMN IF EXISTS university_id')

    op.drop_table('university_olympiads')
    op.drop_table('universities')
    op.drop_table('olympiads')
    op.drop_table('docs')
