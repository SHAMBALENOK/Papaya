"""MVP-расширение: льготы, проверка, сезоны, программы, заявки, версии.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-21

Приводит модель Papaya к требованиям MVP без переписывания существующих
сущностей. Все изменения аддитивные: старые строки получают разумные
значения по умолчанию, новые таблицы необязательны.

Что добавляется:

1. ``university_olympiads`` — правило льготы: вид льготы (``benefit_type``),
   независимый статус проверки (``verification_status`` + кто и когда проверил),
   отдельная отметка подтверждения со стороны вуза (``university_confirmed``),
   обязательный результат, предмет, программы, доп. требования, ссылка на
   источник и срок действия. Существующие связи становятся льготой ``BVI``
   в статусе ``unverified``.
2. ``benefit_rule_versions`` — история версий правила и откат: снимок полей,
   автор, время, причина, статус проверки и источник на момент изменения.
3. ``representative_applications`` — заявка на роль представителя вуза:
   подача, рассмотрение, решение администратора.
4. ``olympiad_seasons`` — сезон олимпиады: год, уровень РСОШ, даты, состояние.
5. ``olympiad_profiles`` — профиль внутри конкретного сезона.
6. ``university_programs`` — программы/направления вуза для фильтров.
7. ``docs`` — независимый статус доступности документа (``availability``).

Сезон и профиль — разные сущности (требование ТЗ): уровень РСОШ, даты и
профили относятся к сезону, а не к олимпиаде, и не переносятся автоматически
из прошлого года в новый.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Правило льготы: новые поля связи БВИ.
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS benefit_type VARCHAR NOT NULL DEFAULT 'BVI'"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS verification_status VARCHAR "
        "NOT NULL DEFAULT 'unverified'"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS verified_by UUID"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS university_confirmed BOOLEAN "
        "NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS university_confirmed_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS result_requirement VARCHAR"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS subject VARCHAR"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS programs JSONB"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS extra_requirements TEXT"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS source_url VARCHAR"
    )
    op.execute(
        "ALTER TABLE university_olympiads "
        "ADD COLUMN IF NOT EXISTS valid_until DATE"
    )
    op.execute(
        'DO $$ BEGIN '
        'ALTER TABLE university_olympiads '
        'ADD CONSTRAINT fk_university_olympiads_verified_by '
        'FOREIGN KEY (verified_by) REFERENCES users (id) ON DELETE SET NULL; '
        'EXCEPTION WHEN duplicate_object THEN NULL; END $$'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_university_olympiads_verification_status '
        'ON university_olympiads (verification_status)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_university_olympiads_benefit_type '
        'ON university_olympiads (benefit_type)'
    )

    # 2. История версий правила льготы.
    op.create_table(
        'benefit_rule_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'link_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('university_olympiads.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column(
            'snapshot',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            'changed_by',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.String(), nullable=True),
        sa.Column('source_doc_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_rollback', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rule_versions_link_id '
        'ON benefit_rule_versions (link_id)'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_benefit_rule_versions_link_version '
        'ON benefit_rule_versions (link_id, version)'
    )

    # 3. Заявки на роль представителя.
    op.create_table(
        'representative_applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'university_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('universities.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('motivation', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column(
            'reviewed_by',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_representative_applications_user_id '
        'ON representative_applications (user_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_representative_applications_university_id '
        'ON representative_applications (university_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_representative_applications_status '
        'ON representative_applications (status)'
    )
    # Не более одной активной заявки на пару (пользователь, вуз).
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS '
        'uq_representative_applications_pending_user_university '
        "ON representative_applications (user_id, university_id) "
        "WHERE status = 'PENDING'"
    )

    # 4. Сезоны олимпиады.
    op.create_table(
        'olympiad_seasons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'olympiad_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('olympiads.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('rsoh_level', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=False, server_default='unknown'),
        sa.Column('dates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('source_doc_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_olympiad_seasons_olympiad_id '
        'ON olympiad_seasons (olympiad_id)'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_olympiad_seasons_olympiad_year '
        'ON olympiad_seasons (olympiad_id, year)'
    )

    # 5. Профили сезона.
    op.create_table(
        'olympiad_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'season_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('olympiad_seasons.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('name_norm', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_olympiad_profiles_season_id '
        'ON olympiad_profiles (season_id)'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_olympiad_profiles_season_name '
        'ON olympiad_profiles (season_id, name_norm)'
    )

    # 6. Программы/направления вуза.
    op.create_table(
        'university_programs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'university_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('universities.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('name_norm', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_university_programs_university_id '
        'ON university_programs (university_id)'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_university_programs_university_name '
        'ON university_programs (university_id, name_norm)'
    )

    # 7. Статус доступности документа-источника.
    op.execute(
        "ALTER TABLE docs "
        "ADD COLUMN IF NOT EXISTS availability VARCHAR NOT NULL DEFAULT 'unknown'"
    )
    op.execute(
        "ALTER TABLE docs ADD COLUMN IF NOT EXISTS availability_checked_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute('ALTER TABLE docs DROP COLUMN IF EXISTS availability_checked_at')
    op.execute('ALTER TABLE docs DROP COLUMN IF EXISTS availability')

    op.drop_table('university_programs')
    op.drop_table('olympiad_profiles')
    op.drop_table('olympiad_seasons')
    op.drop_table('representative_applications')
    op.drop_table('benefit_rule_versions')

    op.execute(
        'DROP INDEX IF EXISTS ix_university_olympiads_benefit_type'
    )
    op.execute(
        'DROP INDEX IF EXISTS ix_university_olympiads_verification_status'
    )
    op.execute(
        'ALTER TABLE university_olympiads '
        'DROP CONSTRAINT IF EXISTS fk_university_olympiads_verified_by'
    )
    for column in (
        'valid_until', 'source_url', 'extra_requirements', 'programs',
        'subject', 'result_requirement', 'university_confirmed_at',
        'university_confirmed', 'verified_at', 'verified_by',
        'verification_status', 'benefit_type',
    ):
        op.execute(
            f'ALTER TABLE university_olympiads DROP COLUMN IF EXISTS {column}'
        )
