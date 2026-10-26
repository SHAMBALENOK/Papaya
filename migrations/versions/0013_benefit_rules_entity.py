"""Правило льготы как отдельная сущность: сезон, профиль, программы, аудит.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26

Переводит связь «университет — олимпиада» (``university_olympiads``) в
полноценное правило льготы ``benefit_rules`` (ТЗ §4.3, §9, §10):

1. Таблица переименовывается в ``benefit_rules``; индексы и ограничения
   получают имена по новой таблице. Данные сохраняются целиком.
2. Правило ссылается на конкретный сезон (``season_id``) и профиль
   (``profile_id``) олимпиады. Составные внешние ключи гарантируют, что сезон
   принадлежит той же олимпиаде, а профиль — тому же сезону. Для этого на
   ``olympiad_seasons`` и ``olympiad_profiles`` добавляются составные
   уникальные ключи ``(id, olympiad_id)`` / ``(id, season_id)``.
3. Программы правила переезжают из JSONB-списка строк в связь M2M
   ``benefit_rule_programs`` с настоящими записями ``university_programs``
   (недостающие программы создаются по названию). Старая колонка
   ``programs`` удаляется только после переноса.
4. Публикационное состояние: ``PENDING`` → ``draft`` (заявка, которую ещё не
   публиковали), ``CONFIRMED`` → ``published``. Колонка ``confirmedBy``
   становится ``published_by``; добавляется ``published_at``.
5. Уникальность пары заменяется уникальностью содержимого: частичный индекс
   по ``(university_id, olympiad_id, dedup_key)`` для неархивных правил —
   одна пара теперь может иметь несколько правил (сезоны, профили, виды
   льгот, программы), а два одинаковых действующих правила невозможны.
6. ``version`` — номер последней версии для оптимистической блокировки;
   ``verification_note`` — причина отклонения при проверке.
7. ``benefit_rule_versions.link_id`` → ``rule_id``.
8. ``olympiads.organizer``, ``olympiad_seasons.label``.
9. Новые таблицы: ``audit_events`` (персистентный аудит) и
   ``catalog_requests`` (запросы представителей о пополнении каталога).

Все операции идемпотентны (``IF NOT EXISTS`` / проверки каталога), чтобы
миграцию можно было безопасно повторить на частично обновлённой базе.
"""

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def _normalize_name(value: str) -> str:
    """Та же нормализация, что и в приложении (``app.database.search``)."""
    from app.database.search import normalize_name

    return normalize_name(value)


def _table_exists(bind, table: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                'SELECT 1 FROM information_schema.tables '
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {'t': table},
        ).scalar()
    )


def _column_exists(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                'SELECT 1 FROM information_schema.columns '
                "WHERE table_schema = 'public' AND table_name = :t "
                'AND column_name = :c'
            ),
            {'t': table, 'c': column},
        ).scalar()
    )


def _constraint_exists(bind, name: str) -> bool:
    return bool(
        bind.execute(
            sa.text('SELECT 1 FROM pg_constraint WHERE conname = :n'),
            {'n': name},
        ).scalar()
    )


def _index_exists(bind, name: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_class WHERE relkind = 'i' AND relname = :n"),
            {'n': name},
        ).scalar()
    )


def _rename_index(bind, old: str, new: str) -> None:
    if _index_exists(bind, old) and not _index_exists(bind, new):
        op.execute(f'ALTER INDEX {old} RENAME TO {new}')


def _rename_constraint(bind, table: str, old: str, new: str) -> None:
    if _constraint_exists(bind, old) and not _constraint_exists(bind, new):
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Каталог: организатор олимпиады и обозначение сезона.
    op.execute('ALTER TABLE olympiads ADD COLUMN IF NOT EXISTS organizer VARCHAR')
    op.execute('ALTER TABLE olympiad_seasons ADD COLUMN IF NOT EXISTS label VARCHAR')

    # 2. Составные уникальные ключи для целостности «сезон той же олимпиады»,
    #    «профиль того же сезона», «программа того же вуза».
    if not _constraint_exists(bind, 'uq_olympiad_seasons_id_olympiad'):
        op.execute(
            'ALTER TABLE olympiad_seasons ADD CONSTRAINT '
            'uq_olympiad_seasons_id_olympiad UNIQUE (id, olympiad_id)'
        )
    if not _constraint_exists(bind, 'uq_olympiad_profiles_id_season'):
        op.execute(
            'ALTER TABLE olympiad_profiles ADD CONSTRAINT '
            'uq_olympiad_profiles_id_season UNIQUE (id, season_id)'
        )
    if not _constraint_exists(bind, 'uq_university_programs_id_university'):
        op.execute(
            'ALTER TABLE university_programs ADD CONSTRAINT '
            'uq_university_programs_id_university UNIQUE (id, university_id)'
        )

    # 3. Переименование таблицы связи в таблицу правил.
    if _table_exists(bind, 'university_olympiads') and not _table_exists(
        bind, 'benefit_rules'
    ):
        op.execute('ALTER TABLE university_olympiads RENAME TO benefit_rules')
    _rename_constraint(
        bind, 'benefit_rules', 'university_olympiads_pkey', 'benefit_rules_pkey'
    )
    for suffix in ('benefit_type', 'createdat', 'olympiad_id', 'status',
                   'university_id', 'verification_status'):
        _rename_index(
            bind,
            f'ix_university_olympiads_{suffix}',
            f'ix_benefit_rules_{suffix}',
        )
    for old, new in (
        ('fk_university_olympiads_source_doc', 'fk_benefit_rules_source_doc'),
        ('fk_university_olympiads_verified_by', 'fk_benefit_rules_verified_by'),
        ('university_olympiads_createdBy_fkey', 'benefit_rules_createdBy_fkey'),
        ('university_olympiads_olympiad_id_fkey', 'benefit_rules_olympiad_id_fkey'),
        ('university_olympiads_university_id_fkey', 'benefit_rules_university_id_fkey'),
        ('university_olympiads_confirmedBy_fkey', 'benefit_rules_published_by_fkey'),
    ):
        _rename_constraint(bind, 'benefit_rules', old, new)

    # 4. Новые колонки правила.
    if _column_exists(bind, 'benefit_rules', 'confirmedBy') and not _column_exists(
        bind, 'benefit_rules', 'published_by'
    ):
        op.execute('ALTER TABLE benefit_rules RENAME COLUMN "confirmedBy" TO published_by')
    op.execute('ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ')
    op.execute('ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS season_id UUID')
    op.execute('ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS profile_id UUID')
    op.execute(
        'ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS version INTEGER '
        'NOT NULL DEFAULT 0'
    )
    op.execute('ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS dedup_key VARCHAR')
    op.execute('ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS verification_note TEXT')
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rules_season_id ON benefit_rules (season_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_benefit_rules_profile_id ON benefit_rules (profile_id)')

    if not _constraint_exists(bind, 'fk_benefit_rules_season_olympiad'):
        op.execute(
            'ALTER TABLE benefit_rules ADD CONSTRAINT fk_benefit_rules_season_olympiad '
            'FOREIGN KEY (season_id, olympiad_id) '
            'REFERENCES olympiad_seasons (id, olympiad_id)'
        )
    if not _constraint_exists(bind, 'fk_benefit_rules_profile_season'):
        op.execute(
            'ALTER TABLE benefit_rules ADD CONSTRAINT fk_benefit_rules_profile_season '
            'FOREIGN KEY (profile_id, season_id) '
            'REFERENCES olympiad_profiles (id, season_id)'
        )
    if not _constraint_exists(bind, 'ck_benefit_rules_profile_requires_season'):
        op.execute(
            'ALTER TABLE benefit_rules ADD CONSTRAINT '
            'ck_benefit_rules_profile_requires_season '
            'CHECK (profile_id IS NULL OR season_id IS NOT NULL)'
        )

    # 5. Публикационное состояние вместо статуса заявки.
    op.execute("UPDATE benefit_rules SET status = 'draft' WHERE status = 'PENDING'")
    op.execute(
        "UPDATE benefit_rules SET status = 'published', "
        'published_at = COALESCE(published_at, "updatedAt", "createdAt") '
        "WHERE status = 'CONFIRMED'"
    )
    op.execute(
        "UPDATE benefit_rules SET status = 'draft' "
        "WHERE status NOT IN ('draft', 'published', 'archived')"
    )
    op.execute("ALTER TABLE benefit_rules ALTER COLUMN status SET DEFAULT 'draft'")
    if not _constraint_exists(bind, 'ck_benefit_rules_status'):
        op.execute(
            'ALTER TABLE benefit_rules ADD CONSTRAINT ck_benefit_rules_status '
            "CHECK (status IN ('draft', 'published', 'archived'))"
        )
    op.execute(
        "UPDATE benefit_rules SET verification_status = 'unverified' "
        "WHERE verification_status NOT IN ('unverified', 'verified', 'rejected')"
    )
    if not _constraint_exists(bind, 'ck_benefit_rules_verification_status'):
        op.execute(
            'ALTER TABLE benefit_rules ADD CONSTRAINT '
            'ck_benefit_rules_verification_status '
            "CHECK (verification_status IN ('unverified', 'verified', 'rejected'))"
        )

    # 6. Программы правила: M2M с настоящими программами вуза.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_rule_programs (
            rule_id UUID NOT NULL REFERENCES benefit_rules (id) ON DELETE CASCADE,
            program_id UUID NOT NULL,
            university_id UUID NOT NULL,
            PRIMARY KEY (rule_id, program_id),
            CONSTRAINT fk_benefit_rule_programs_program_university
                FOREIGN KEY (program_id, university_id)
                REFERENCES university_programs (id, university_id)
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rule_programs_program_id '
        'ON benefit_rule_programs (program_id)'
    )
    if _column_exists(bind, 'benefit_rules', 'programs'):
        _migrate_program_names(bind)
        op.execute('ALTER TABLE benefit_rules DROP COLUMN programs')

    # 7. Ключ содержимого и номер версии.
    _fill_dedup_keys(bind)
    op.execute("UPDATE benefit_rules SET dedup_key = '' WHERE dedup_key IS NULL")
    op.execute("ALTER TABLE benefit_rules ALTER COLUMN dedup_key SET DEFAULT ''")
    op.execute('ALTER TABLE benefit_rules ALTER COLUMN dedup_key SET NOT NULL')
    if _constraint_exists(bind, 'uq_university_olympiads_pair'):
        op.execute(
            'ALTER TABLE benefit_rules DROP CONSTRAINT uq_university_olympiads_pair'
        )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS ux_benefit_rules_dedup '
        'ON benefit_rules (university_id, olympiad_id, dedup_key) '
        "WHERE status <> 'archived'"
    )

    # 8. История версий: ссылка на правило.
    if _column_exists(bind, 'benefit_rule_versions', 'link_id') and not _column_exists(
        bind, 'benefit_rule_versions', 'rule_id'
    ):
        op.execute('ALTER TABLE benefit_rule_versions RENAME COLUMN link_id TO rule_id')
    _rename_index(
        bind, 'ix_benefit_rule_versions_link_id', 'ix_benefit_rule_versions_rule_id'
    )
    _rename_index(
        bind,
        'uq_benefit_rule_versions_link_version',
        'uq_benefit_rule_versions_rule_version',
    )
    _rename_constraint(
        bind,
        'benefit_rule_versions',
        'benefit_rule_versions_link_id_fkey',
        'benefit_rule_versions_rule_id_fkey',
    )
    op.execute(
        'UPDATE benefit_rules r SET version = v.max_version FROM ('
        'SELECT rule_id, MAX(version) AS max_version '
        'FROM benefit_rule_versions GROUP BY rule_id) v '
        'WHERE v.rule_id = r.id AND r.version < v.max_version'
    )

    # 9. Аудит и запросы о пополнении каталога.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id UUID PRIMARY KEY,
            action VARCHAR NOT NULL,
            actor_id UUID REFERENCES users (id) ON DELETE SET NULL,
            target_type VARCHAR,
            target_id VARCHAR,
            details JSONB,
            ip VARCHAR,
            request_id VARCHAR,
            "createdAt" TIMESTAMPTZ
        )
        """
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_audit_events_action ON audit_events (action)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_audit_events_actor_id ON audit_events (actor_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_audit_events_target_id ON audit_events (target_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_audit_events_createdat ON audit_events ("createdAt")')

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_requests (
            id UUID PRIMARY KEY,
            university_id UUID NOT NULL REFERENCES universities (id) ON DELETE CASCADE,
            user_id UUID REFERENCES users (id) ON DELETE SET NULL,
            kind VARCHAR NOT NULL DEFAULT 'olympiad',
            olympiad_id UUID REFERENCES olympiads (id) ON DELETE SET NULL,
            text TEXT NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'open',
            admin_note TEXT,
            resolved_by UUID REFERENCES users (id) ON DELETE SET NULL,
            resolved_at TIMESTAMPTZ,
            "createdAt" TIMESTAMPTZ,
            "updatedAt" TIMESTAMPTZ
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_catalog_requests_university_id '
        'ON catalog_requests (university_id)'
    )
    op.execute('CREATE INDEX IF NOT EXISTS ix_catalog_requests_status ON catalog_requests (status)')
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_catalog_requests_createdat '
        'ON catalog_requests ("createdAt")'
    )


def _migrate_program_names(bind) -> None:
    """Перенести JSONB-список названий программ в M2M с ``university_programs``.

    Название сопоставляется с существующей программой вуза по ``name_norm``;
    если такой нет — программа создаётся. Так старые правила не теряют область
    действия, а каталог программ пополняется реальными записями.
    """
    rows = bind.execute(
        sa.text(
            'SELECT id, university_id, programs FROM benefit_rules '
            'WHERE programs IS NOT NULL'
        )
    ).fetchall()
    if not rows:
        return

    existing = {}
    for program_id, university_id, name_norm in bind.execute(
        sa.text('SELECT id, university_id, name_norm FROM university_programs')
    ).fetchall():
        existing[(str(university_id), name_norm)] = program_id

    for rule_id, university_id, programs in rows:
        if isinstance(programs, str):
            try:
                programs = json.loads(programs)
            except ValueError:
                programs = [programs]
        if not isinstance(programs, list):
            continue
        for raw in programs:
            name = str(raw or '').strip()
            name_norm = _normalize_name(name)
            if not name_norm:
                continue
            key = (str(university_id), name_norm)
            program_id = existing.get(key)
            if program_id is None:
                program_id = uuid.uuid4()
                bind.execute(
                    sa.text(
                        'INSERT INTO university_programs '
                        '(id, university_id, name, name_norm, "createdAt", "updatedAt") '
                        'VALUES (:id, :u, :name, :norm, now(), now())'
                    ),
                    {'id': program_id, 'u': university_id, 'name': name, 'norm': name_norm},
                )
                existing[key] = program_id
            bind.execute(
                sa.text(
                    'INSERT INTO benefit_rule_programs (rule_id, program_id, university_id) '
                    'VALUES (:r, :p, :u) ON CONFLICT DO NOTHING'
                ),
                {'r': rule_id, 'p': program_id, 'u': university_id},
            )


def _fill_dedup_keys(bind) -> None:
    """Вычислить ключ содержимого для существующих правил.

    Формула совпадает с ``app.database.benefit_rules.build_dedup_key``; она
    продублирована здесь, чтобы миграция не зависела от будущих правок кода.
    """
    rows = bind.execute(
        sa.text(
            'SELECT r.id, r.season_id, r.profile_id, r.benefit_type, '
            'r.result_requirement, r.subject, '
            "COALESCE(string_agg(p.program_id::text, ',' ORDER BY p.program_id::text), '') "
            'FROM benefit_rules r '
            'LEFT JOIN benefit_rule_programs p ON p.rule_id = r.id '
            'WHERE r.dedup_key IS NULL '
            'GROUP BY r.id'
        )
    ).fetchall()
    for rule_id, season_id, profile_id, benefit_type, result, subject, programs in rows:
        key = '|'.join(
            [
                str(season_id) if season_id else '-',
                str(profile_id) if profile_id else '-',
                benefit_type or 'BVI',
                _normalize_name(result or '') or '-',
                _normalize_name(subject or '') or '-',
                programs or '-',
            ]
        )
        bind.execute(
            sa.text('UPDATE benefit_rules SET dedup_key = :k WHERE id = :id'),
            {'k': key, 'id': rule_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute('DROP TABLE IF EXISTS catalog_requests')
    op.execute('DROP TABLE IF EXISTS audit_events')

    # Программы обратно в JSONB-список названий.
    op.execute('ALTER TABLE benefit_rules ADD COLUMN IF NOT EXISTS programs JSONB')
    op.execute(
        'UPDATE benefit_rules r SET programs = sub.names FROM ('
        'SELECT bp.rule_id, jsonb_agg(up.name ORDER BY up.name_norm) AS names '
        'FROM benefit_rule_programs bp '
        'JOIN university_programs up ON up.id = bp.program_id '
        'GROUP BY bp.rule_id) sub WHERE sub.rule_id = r.id'
    )
    op.execute('DROP TABLE IF EXISTS benefit_rule_programs')

    op.execute('DROP INDEX IF EXISTS ux_benefit_rules_dedup')
    # Архивные правила могли нарушать уникальность пары: оставляем самое новое.
    op.execute(
        'DELETE FROM benefit_rules a USING benefit_rules b '
        'WHERE a.university_id = b.university_id AND a.olympiad_id = b.olympiad_id '
        'AND a."createdAt" < b."createdAt"'
    )
    if not _constraint_exists(bind, 'uq_university_olympiads_pair'):
        op.execute(
            'ALTER TABLE benefit_rules ADD CONSTRAINT uq_university_olympiads_pair '
            'UNIQUE (university_id, olympiad_id)'
        )

    for name in (
        'ck_benefit_rules_verification_status',
        'ck_benefit_rules_status',
        'ck_benefit_rules_profile_requires_season',
        'fk_benefit_rules_profile_season',
        'fk_benefit_rules_season_olympiad',
    ):
        if _constraint_exists(bind, name):
            op.execute(f'ALTER TABLE benefit_rules DROP CONSTRAINT {name}')

    op.execute("UPDATE benefit_rules SET status = 'PENDING' WHERE status = 'draft'")
    op.execute(
        "UPDATE benefit_rules SET status = 'CONFIRMED' "
        "WHERE status IN ('published', 'archived')"
    )
    op.execute("ALTER TABLE benefit_rules ALTER COLUMN status SET DEFAULT 'PENDING'")

    for column in ('season_id', 'profile_id', 'version', 'dedup_key',
                   'verification_note', 'published_at'):
        op.execute(f'ALTER TABLE benefit_rules DROP COLUMN IF EXISTS {column}')
    if _column_exists(bind, 'benefit_rules', 'published_by'):
        op.execute('ALTER TABLE benefit_rules RENAME COLUMN published_by TO "confirmedBy"')

    if _column_exists(bind, 'benefit_rule_versions', 'rule_id'):
        op.execute('ALTER TABLE benefit_rule_versions RENAME COLUMN rule_id TO link_id')
    _rename_index(
        bind, 'ix_benefit_rule_versions_rule_id', 'ix_benefit_rule_versions_link_id'
    )
    _rename_index(
        bind,
        'uq_benefit_rule_versions_rule_version',
        'uq_benefit_rule_versions_link_version',
    )

    if _table_exists(bind, 'benefit_rules') and not _table_exists(
        bind, 'university_olympiads'
    ):
        op.execute('ALTER TABLE benefit_rules RENAME TO university_olympiads')

    for name in (
        'uq_university_programs_id_university',
        'uq_olympiad_profiles_id_season',
        'uq_olympiad_seasons_id_olympiad',
    ):
        table = {
            'uq_university_programs_id_university': 'university_programs',
            'uq_olympiad_profiles_id_season': 'olympiad_profiles',
            'uq_olympiad_seasons_id_olympiad': 'olympiad_seasons',
        }[name]
        if _constraint_exists(bind, name):
            op.execute(f'ALTER TABLE {table} DROP CONSTRAINT {name}')

    op.execute('ALTER TABLE olympiad_seasons DROP COLUMN IF EXISTS label')
    op.execute('ALTER TABLE olympiads DROP COLUMN IF EXISTS organizer')
