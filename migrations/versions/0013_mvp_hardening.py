"""MVP hardening: источники, запуски импорта, архивы, индексы и инварианты.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- документы: автор загрузки --------------------------------------
    op.add_column(
        'docs',
        sa.Column(
            'uploaded_by',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_docs_uploaded_by ON docs (uploaded_by)')

    # --- олимпиады: организатор -----------------------------------------
    op.add_column('olympiads', sa.Column('organizer', sa.String(), nullable=True))

    # --- вузы и программы: архив ----------------------------------------
    op.add_column(
        'universities',
        sa.Column(
            'is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_universities_is_archived ON universities (is_archived)'
    )
    op.add_column(
        'university_programs',
        sa.Column(
            'is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_university_programs_is_archived '
        'ON university_programs (is_archived)'
    )

    # --- сезоны: архив ---------------------------------------------------
    op.add_column(
        'olympiad_seasons',
        sa.Column(
            'is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_olympiad_seasons_is_archived '
        'ON olympiad_seasons (is_archived)'
    )
    # Перед уникальным ограничением разводим уже существующие дубли: две
    # записи «2024» у одной олимпиады раньше были допустимы и могли остаться
    # в рабочей базе. Переименовываем только повторы (по createdAt, затем id),
    # сохраняя все связи: удалять сезон вместе с профилями и правилами нельзя.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY olympiad_id, season_label
                       ORDER BY "createdAt" NULLS LAST, id
                   ) AS rn
            FROM olympiad_seasons
        )
        UPDATE olympiad_seasons AS s
        SET season_label = s.season_label || ' (' || left(s.id::text, 8) || ')'
        FROM ranked AS r
        WHERE s.id = r.id AND r.rn > 1
        """
    )
    op.create_unique_constraint(
        'uq_olympiad_seasons_olympiad_label',
        'olympiad_seasons',
        ['olympiad_id', 'season_label'],
    )

    # --- источники -------------------------------------------------------
    op.create_table(
        'sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=False, server_default='OTHER'),
        sa.Column(
            'university_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('universities.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'doc_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('docs.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_sources_kind ON sources (kind)')
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_sources_university_id ON sources (university_id)'
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_sources_createdAt ON sources ("createdAt")')

    # --- правила льгот: структурированный результат и источник ----------
    op.add_column(
        'benefit_rules', sa.Column('required_result_type', sa.String(), nullable=True)
    )
    op.add_column(
        'benefit_rules', sa.Column('required_result_value', sa.String(), nullable=True)
    )
    op.add_column(
        'benefit_rules',
        sa.Column(
            'source_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('sources.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_season_id '
        'ON benefit_rules (season_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_profile_id '
        'ON benefit_rules (profile_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_subject '
        'ON benefit_rules (subject)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_is_published '
        'ON benefit_rules (is_published)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_createdAt '
        'ON benefit_rules ("createdAt")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_public_lookup '
        'ON benefit_rules (university_id, verification_status, is_published)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_source_id '
        'ON benefit_rules (source_id)'
    )
    op.create_unique_constraint(
        'uq_benefit_rule_versions_rule_version',
        'benefit_rule_versions',
        ['rule_id', 'version_number'],
    )
    # Нормализуем значения, которые могли попасть в базу до появления
    # allowlist-ов: CHECK не должен падать на легаси-данных.
    op.execute(
        """
        UPDATE benefit_rules
        SET benefit_type = CASE
            WHEN lower(benefit_type) IN ('бви', 'без вступительных', 'bvi') THEN 'BVI'
            WHEN lower(benefit_type) IN ('100 егэ', '100 баллов егэ', 'ege_100') THEN 'EGE_100'
            WHEN lower(benefit_type) IN ('100 дви', '100 баллов дви', 'dvi_100') THEN 'DVI_100'
            WHEN lower(benefit_type) IN ('другие', 'другие преимущества', 'other') THEN 'OTHER'
            WHEN benefit_type NOT IN ('BVI', 'EGE_100', 'DVI_100', 'OTHER') THEN 'OTHER'
            ELSE benefit_type
        END
        """
    )
    op.execute(
        """
        UPDATE benefit_rules
        SET verification_status = CASE
            WHEN lower(verification_status) IN ('непроверено', 'не проверено') THEN 'unverified'
            WHEN lower(verification_status) IN ('проверено') THEN 'verified'
            WHEN lower(verification_status) IN ('отклонено') THEN 'rejected'
            WHEN verification_status NOT IN ('unverified', 'verified', 'rejected') THEN 'unverified'
            ELSE verification_status
        END
        """
    )
    op.create_check_constraint(
        'ck_benefit_rules_type',
        'benefit_rules',
        "benefit_type IN ('BVI', 'EGE_100', 'DVI_100', 'OTHER')",
    )
    op.create_check_constraint(
        'ck_benefit_rules_status',
        'benefit_rules',
        "verification_status IN ('unverified', 'verified', 'rejected')",
    )

    # --- история запусков импорта ---------------------------------------
    op.create_table(
        'import_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'doc_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('docs.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('kind', sa.String(), nullable=False, server_default='RSOSH'),
        sa.Column('status', sa.String(), nullable=False, server_default='PROCESSING'),
        sa.Column(
            'started_by',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_import_jobs_doc_id ON import_jobs (doc_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_import_jobs_status ON import_jobs (status)')
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_import_jobs_started_at ON import_jobs (started_at)'
    )

    op.create_table(
        'import_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'job_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('import_jobs.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('action', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_import_records_job_id ON import_records (job_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_import_records_createdAt '
        'ON import_records ("createdAt")'
    )


def downgrade() -> None:
    op.drop_constraint('ck_benefit_rules_status', 'benefit_rules', type_='check')
    op.drop_constraint('ck_benefit_rules_type', 'benefit_rules', type_='check')
    op.drop_constraint(
        'uq_benefit_rule_versions_rule_version',
        'benefit_rule_versions',
        type_='unique',
    )
    op.drop_column('benefit_rules', 'source_id')
    op.drop_column('benefit_rules', 'required_result_value')
    op.drop_column('benefit_rules', 'required_result_type')
    op.drop_table('import_records')
    op.drop_table('import_jobs')
    op.drop_table('sources')
    op.drop_constraint(
        'uq_olympiad_seasons_olympiad_label',
        'olympiad_seasons',
        type_='unique',
    )
    op.drop_column('olympiad_seasons', 'is_archived')
    op.drop_column('university_programs', 'is_archived')
    op.drop_column('universities', 'is_archived')
    op.drop_column('olympiads', 'organizer')
    op.drop_column('docs', 'uploaded_by')
