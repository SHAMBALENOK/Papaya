"""MVP: удаление legacy-схемы после переноса данных.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-14

Перед удалением миграция проверяет, что перенос состоялся и ничего не потеряно:

* у каждой старой связи ``university_olympiads`` есть правило льготы;
* каждый ``source_id``, у которого был документ, превратился в ``doc_id``;
* сезон правила принадлежит олимпиаде правила, профиль — сезону;
* документ-основание принадлежит тому же университету.

При расхождении миграция падает с понятным сообщением: удалять схему, в
которой остались неперенесённые данные, нельзя. Сырые строки удаляемых таблиц
и значения удаляемых колонок предварительно складываются в
``migration_archive``, поэтому даже после ``DROP`` исходную информацию можно
поднять.

Удаляются:

* ``university_olympiads`` — отдельная сущность БВИ;
* ``sources`` — отдельная сущность источника;
* ``benefit_rule_programs`` — связь правил с программами;
* даты и ``availability`` сезона, ``rsosh_level`` сезона;
* ``discipline``/``subject``/``profile_name``/``extra_params`` профиля;
* свободный текст результата, предмет, дополнительные требования,
  ``source_url``/``source_id`` правила и ``source_url`` версии;
* ``olympiads.source_url``.

``olympiads.source_doc_id`` остаётся: это техническая связь импортёра РСОШ и
одновременно публичное «откуда взята информация».
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def _scalar(bind, sql: str) -> int:
    return int(bind.execute(sa.text(sql)).scalar_one())


def _check_integrity(bind) -> None:
    problems = []

    orphans = _scalar(
        bind,
        """
        SELECT count(*) FROM university_olympiads uo
        WHERE NOT EXISTS (
            SELECT 1 FROM benefit_rules br
            WHERE br.university_id = uo.university_id
              AND br.olympiad_id = uo.olympiad_id
              AND br.benefit_type = 'BVI'
        )
        """,
    )
    if orphans:
        problems.append(
            f'{orphans} связей university_olympiads не имеют правила льготы'
        )

    lost_sources = _scalar(
        bind,
        """
        SELECT count(*) FROM benefit_rules br
        JOIN sources s ON s.id = br.source_id
        WHERE br.doc_id IS NULL AND s.doc_id IS NOT NULL
        """,
    )
    if lost_sources:
        problems.append(
            f'{lost_sources} правил потеряли документ при переносе source_id'
        )

    wrong_season = _scalar(
        bind,
        """
        SELECT count(*) FROM benefit_rules br
        JOIN olympiad_seasons s ON s.id = br.season_id
        WHERE s.olympiad_id <> br.olympiad_id
        """,
    )
    if wrong_season:
        problems.append(
            f'{wrong_season} правил ссылаются на сезон другой олимпиады'
        )

    wrong_profile = _scalar(
        bind,
        """
        SELECT count(*) FROM benefit_rules br
        JOIN season_profiles p ON p.id = br.profile_id
        WHERE br.season_id IS NULL OR p.season_id <> br.season_id
        """,
    )
    if wrong_profile:
        problems.append(
            f'{wrong_profile} правил ссылаются на профиль другого сезона'
        )

    wrong_doc = _scalar(
        bind,
        """
        SELECT count(*) FROM benefit_rules br
        JOIN docs d ON d.id = br.doc_id
        WHERE d.university_id IS DISTINCT FROM br.university_id
        """,
    )
    if wrong_doc:
        problems.append(
            f'{wrong_doc} правил ссылаются на документ другого университета'
        )

    if problems:
        raise RuntimeError(
            'Перенос в каноническую модель неполон, удаление legacy-схемы '
            'отменено:\n- ' + '\n- '.join(problems)
        )


def _archive_table(bind, table: str, entity_type: str, has_id: bool) -> None:
    if has_id:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO migration_archive
                    (id, entity_type, entity_id, field, old_value, note,
                     "createdAt")
                SELECT gen_random_uuid(), :entity_type, t.id, 'row',
                       to_jsonb(t), :note, now()
                FROM {table} t
                """
            ),
            {
                'entity_type': entity_type,
                'note': f'Сырая строка удалённой таблицы {table}',
            },
        )
    else:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO migration_archive
                    (id, entity_type, entity_id, field, old_value, note,
                     "createdAt")
                SELECT gen_random_uuid(), :entity_type, NULL, 'row',
                       to_jsonb(t), :note, now()
                FROM {table} t
                """
            ),
            {
                'entity_type': entity_type,
                'note': f'Сырая строка удалённой таблицы {table}',
            },
        )


def _archive_columns(bind) -> None:
    """Сохранить значения колонок, которые будут удалены."""
    pairs = (
        (
            'olympiad_seasons',
            'olympiad_season',
            ('rsosh_level', 'registration_start', 'registration_end',
             'event_start', 'event_end', 'extra_params', 'availability'),
        ),
        (
            'season_profiles',
            'season_profile',
            ('discipline', 'subject', 'profile_name', 'extra_params'),
        ),
        (
            'benefit_rules',
            'benefit_rule',
            ('required_result', 'required_result_value', 'subject',
             'additional_requirements', 'source_url', 'source_id'),
        ),
        ('benefit_rule_versions', 'benefit_rule_version', ('source_url',)),
        ('olympiads', 'olympiad', ('source_url',)),
    )
    for table, entity_type, columns in pairs:
        for column in columns:
            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO migration_archive
                        (id, entity_type, entity_id, field, old_value, note,
                         "createdAt")
                    SELECT gen_random_uuid(), :entity_type, t.id, :field,
                           to_jsonb(t.{column}), :note, now()
                    FROM {table} t
                    WHERE t.{column} IS NOT NULL
                    """
                ),
                {
                    'entity_type': entity_type,
                    'field': column,
                    'note': f'Значение колонки {table}.{column} до удаления',
                },
            )


def _drop_legacy(bind) -> None:
    # Сначала архивируем, потом удаляем. Порядок удаления — от зависимых к
    # независимым: связь правил с программами, колонка source_id (FK), sources.
    _archive_table(bind, 'university_olympiads', 'university_olympiad', True)
    _archive_table(bind, 'sources', 'source', True)
    _archive_table(bind, 'benefit_rule_programs', 'benefit_rule_program', False)
    _archive_columns(bind)

    op.execute('DROP TABLE IF EXISTS benefit_rule_programs')
    op.execute('DROP INDEX IF EXISTS ix_benefit_rules_source_id')
    op.execute('ALTER TABLE benefit_rules DROP COLUMN IF EXISTS source_id')
    op.execute('DROP TABLE IF EXISTS sources')
    op.execute('DROP TABLE IF EXISTS university_olympiads')

    op.execute('DROP INDEX IF EXISTS uq_benefit_rules_base_published')
    op.execute('DROP INDEX IF EXISTS ix_benefit_rules_subject')

    op.execute(
        """
        ALTER TABLE olympiad_seasons
            DROP COLUMN IF EXISTS rsosh_level,
            DROP COLUMN IF EXISTS registration_start,
            DROP COLUMN IF EXISTS registration_end,
            DROP COLUMN IF EXISTS event_start,
            DROP COLUMN IF EXISTS event_end,
            DROP COLUMN IF EXISTS extra_params,
            DROP COLUMN IF EXISTS availability
        """
    )
    op.execute(
        """
        ALTER TABLE season_profiles
            DROP COLUMN IF EXISTS discipline,
            DROP COLUMN IF EXISTS subject,
            DROP COLUMN IF EXISTS profile_name,
            DROP COLUMN IF EXISTS extra_params
        """
    )
    op.execute(
        """
        ALTER TABLE benefit_rules
            DROP COLUMN IF EXISTS required_result,
            DROP COLUMN IF EXISTS required_result_value,
            DROP COLUMN IF EXISTS subject,
            DROP COLUMN IF EXISTS additional_requirements,
            DROP COLUMN IF EXISTS source_url
        """
    )
    op.execute(
        'ALTER TABLE benefit_rule_versions DROP COLUMN IF EXISTS source_url'
    )
    op.execute('ALTER TABLE olympiads DROP COLUMN IF EXISTS source_url')


def _add_new_invariants() -> None:
    # Одна опубликованная льгота на «вуз + олимпиада + сезон + профиль + тип».
    # NULL-сезон/профиль исключены: это исторические записи, ждущие проверки.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_benefit_rules_scoped_published
        ON benefit_rules (
            university_id, olympiad_id, season_id, profile_id, benefit_type
        )
        WHERE season_id IS NOT NULL
          AND profile_id IS NOT NULL
          AND is_published
        """
    )
    # Публичный каталог фильтрует одновременно по вузу, олимпиаде и сезону.
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_catalog '
        'ON benefit_rules (university_id, olympiad_id, season_id, profile_id)'
    )


def upgrade() -> None:
    bind = op.get_bind()
    _check_integrity(bind)
    _drop_legacy(bind)
    _add_new_invariants()


def downgrade() -> None:
    """Вернуть схему legacy-полей.

    Данные из удалённых таблиц остаются в ``migration_archive``: автоматически
    восстановить их в исходные таблицы нельзя без риска перепутать источники.
    Downgrade восстанавливает структуру, чтобы приложение предыдущей версии
    могло работать, и оставляет наполнение архивом.
    """
    op.execute('DROP INDEX IF EXISTS uq_benefit_rules_scoped_published')
    op.execute('DROP INDEX IF EXISTS ix_benefit_rules_catalog')

    op.add_column('olympiads', sa.Column('source_url', sa.String(), nullable=True))

    op.add_column(
        'benefit_rule_versions',
        sa.Column('source_url', sa.String(), nullable=True),
    )
    for column, type_ in (
        ('required_result', sa.String()),
        ('required_result_value', sa.String()),
        ('subject', sa.String()),
        ('additional_requirements', sa.Text()),
        ('source_url', sa.String()),
    ):
        op.add_column('benefit_rules', sa.Column(column, type_, nullable=True))

    for column, type_ in (
        ('discipline', sa.String()),
        ('subject', sa.String()),
        ('profile_name', sa.String()),
        ('extra_params', postgresql.JSONB(astext_type=sa.Text())),
    ):
        op.add_column('season_profiles', sa.Column(column, type_, nullable=True))

    op.add_column(
        'olympiad_seasons',
        sa.Column('rsosh_level', sa.String(), nullable=True),
    )
    for column in (
        'registration_start', 'registration_end', 'event_start', 'event_end',
    ):
        op.add_column(
            'olympiad_seasons',
            sa.Column(column, sa.DateTime(timezone=True), nullable=True),
        )
    op.add_column(
        'olympiad_seasons',
        sa.Column(
            'extra_params',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        'olympiad_seasons',
        sa.Column(
            'availability', sa.String(), nullable=False, server_default='unknown'
        ),
    )

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
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_source_id '
        'ON benefit_rules (source_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_subject '
        'ON benefit_rules (subject)'
    )

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
        sa.Column(
            'status', sa.String(), nullable=False, server_default='PENDING'
        ),
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
            'university_id', 'olympiad_id',
            name='uq_university_olympiads_pair',
        ),
    )
    op.create_table(
        'benefit_rule_programs',
        sa.Column(
            'rule_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('benefit_rules.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column(
            'program_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('university_programs.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.UniqueConstraint(
            'rule_id', 'program_id', name='uq_benefit_rule_programs_pair'
        ),
    )
    # Историческая защита «одно основное правило на пару».
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_benefit_rules_base_published
        ON benefit_rules (university_id, olympiad_id, benefit_type)
        WHERE season_id IS NULL
          AND profile_id IS NULL
          AND is_published
        """
    )
