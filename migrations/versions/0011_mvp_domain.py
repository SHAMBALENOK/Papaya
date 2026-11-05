"""MVP domain: сезоны, профили, программы, правила льгот, версии, заявки представителей.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('docs', sa.Column('university_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('universities.id', ondelete='SET NULL'), nullable=True))
    op.execute('CREATE INDEX IF NOT EXISTS ix_docs_university_id ON docs (university_id)')

    op.create_table(
        'olympiad_seasons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('olympiad_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('olympiads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('season_label', sa.String(), nullable=False),
        sa.Column('rsosh_level', sa.String(), nullable=True),
        sa.Column('registration_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('registration_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('event_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('event_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('availability', sa.String(), nullable=False, server_default='unknown'),
        sa.Column('source_doc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('docs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_olympiad_seasons_olympiad_id ON olympiad_seasons (olympiad_id)')

    op.create_table(
        'season_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('olympiad_seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('discipline', sa.String(), nullable=True),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('profile_name', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('extra_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_season_profiles_season_id ON season_profiles (season_id)')

    op.create_table(
        'university_programs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('university_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('universities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('name_norm', sa.String(), nullable=False),
        sa.Column('code', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('university_id', 'name_norm', name='uq_university_programs_pair'),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_university_programs_university_id ON university_programs (university_id)')

    op.create_table(
        'benefit_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('university_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('universities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('olympiad_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('olympiads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('olympiad_seasons.id', ondelete='SET NULL'), nullable=True),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('season_profiles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('benefit_type', sa.String(), nullable=False, server_default='BVI'),
        sa.Column('required_result', sa.String(), nullable=True),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('additional_requirements', sa.Text(), nullable=True),
        sa.Column('doc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('docs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('verification_status', sa.String(), nullable=False, server_default='unverified'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rules_university_id ON benefit_rules (university_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rules_olympiad_id ON benefit_rules (olympiad_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rules_verification_status ON benefit_rules (verification_status)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rules_benefit_type ON benefit_rules (benefit_type)')

    op.create_table(
        'benefit_rule_programs',
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('benefit_rules.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('university_programs.id', ondelete='CASCADE'), primary_key=True),
        sa.UniqueConstraint('rule_id', 'program_id', name='uq_benefit_rule_programs_pair'),
    )

    op.create_table(
        'benefit_rule_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('benefit_rules.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('changed_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.String(), nullable=True),
        sa.Column('doc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('docs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rule_versions_rule_id ON benefit_rule_versions (rule_id)')

    op.create_table(
        'benefit_status_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('benefit_rules.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_status', sa.String(), nullable=True),
        sa.Column('to_status', sa.String(), nullable=False),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_status_history_rule_id ON benefit_status_history (rule_id)')

    op.create_table(
        'representative_applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('university_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('universities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('justification', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_representative_applications_user_id ON representative_applications (user_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_representative_applications_status ON representative_applications (status)')


def downgrade() -> None:
    for t in ('representative_applications', 'benefit_status_history', 'benefit_rule_versions',
              'benefit_rule_programs', 'benefit_rules', 'university_programs',
              'season_profiles', 'olympiad_seasons'):
        op.drop_table(t)