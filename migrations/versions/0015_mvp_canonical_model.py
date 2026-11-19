"""MVP: каноническая модель профилей сезона, ЕГЭ и ручной проверки.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-14

Миграция аддитивная: она ничего не удаляет, а приводит существующие данные к
новой модели. Удаление старых таблиц и колонок вынесено в ``0016``, чтобы
сначала можно было проверить результат переноса.

Что делает миграция:

1. Профиль сезона получает ``name``/``name_norm`` и собственный
   ``rsosh_level``. Уровень РСОШ принадлежит профилю конкретного сезона, а не
   олимпиаде и не сезону целиком. Если у сезона ровно один профиль, старый
   ``olympiad_seasons.rsosh_level`` переносится в него; во всех остальных
   случаях значение архивируется и не размножается по профилям, которых оно
   не описывает.
2. Дубли профилей внутри сезона сливаются: правила переводятся на оставшийся
   профиль, исходная строка сохраняется в ``migration_archive`` и только потом
   удаляется. Без этого уникальный индекс «сезон + нормализованное название»
   не построить.
3. Свободный текст ``benefit_rules.required_result`` преобразуется в
   структурированный ``required_result_type``. Неоднозначные значения не
   угадываются: они попадают в очередь ``benefit_rule_migration_issues`` и
   правило помечается ``needs_review``.
4. ``additional_requirements`` разбирается в отдельную запись
   ``benefit_ege_requirements`` только при однозначном виде «ЕГЭ по предмету
   от N». Всё остальное архивируется как текст и требует ручного разбора.
5. Старые ``source_id``/``source_url`` у правила переводятся в ``docs``-документ,
   если источник уже связан с документом того же вуза. Иначе значение
   архивируется: выдумывать документ нельзя.
6. Правила без сезона или профиля (перенесённые из старой модели БВИ) не
   удаляются: они получают ``needs_review = true`` и ждут заполнения в
   админке.
"""

import json
import re
import unicodedata
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


_SPACES = re.compile(r'\s+')
_EDGE_PUNCT = re.compile(r'^[\s\W_]+|[\s\W_]+$', re.UNICODE)
_INNER_PUNCT = re.compile(r'[\s\W_]+', re.UNICODE)

_RESULT_ALIASES = {
    'победитель': 'WINNER',
    'призёр': 'PRIZE',
    'призер': 'PRIZE',
    'победитель или призёр': 'WINNER_OR_PRIZE',
    'победитель или призер': 'WINNER_OR_PRIZE',
    'winner': 'WINNER',
    'prize': 'PRIZE',
    'winner_or_prize': 'WINNER_OR_PRIZE',
}

#: Однозначный вид требования ЕГЭ: «ЕГЭ по математике от 75».
_EGE_RE = re.compile(
    r'^\s*ЕГЭ\s+по\s+(?P<subject>[^,;.]+?)\s*'
    r'(?:от|не\s+менее|минимум)\s*(?P<score>\d{1,3})\s*балл\w*\s*$',
    re.IGNORECASE,
)
_EGE_SUBJECT_RE = re.compile(r'^\s*ЕГЭ\s+по\s+(?P<subject>[^,;.]+)\s*$', re.IGNORECASE)


def _normalize_name(value):
    """Собственная копия правила нормализации: миграция не зависит от кода."""
    text = _SPACES.sub(' ', value or '').strip().casefold().replace('ё', 'е')
    text = unicodedata.normalize('NFKC', text)
    text = _EDGE_PUNCT.sub('', text)
    return _INNER_PUNCT.sub(' ', text).strip()


def _clean_subject(value):
    return (value or '').strip().strip('.,;:—-').strip()


def _archive_json(bind, entity_type, entity_id, field, old_json, note):
    bind.execute(
        sa.text(
            """
            INSERT INTO migration_archive
                (id, entity_type, entity_id, field, old_value, note, "createdAt")
            VALUES
                (:id, :entity_type, :entity_id, :field,
                 CAST(:old_value AS jsonb), :note, now())
            """
        ),
        {
            'id': uuid.uuid4(),
            'entity_type': entity_type,
            'entity_id': entity_id,
            'field': field,
            'old_value': old_json,
            'note': note,
        },
    )


def _issue(bind, rule_id, field, raw_value, reason):
    bind.execute(
        sa.text(
            """
            INSERT INTO benefit_rule_migration_issues
                (id, rule_id, entity_type, entity_id, field, raw_value, reason,
                 resolved, "createdAt")
            VALUES
                (:id, :rule_id, 'benefit_rule', :rule_id, :field, :raw_value,
                 :reason, false, now())
            """
        ),
        {
            'id': uuid.uuid4(),
            'rule_id': rule_id,
            'field': field,
            'raw_value': None if raw_value is None else str(raw_value),
            'reason': reason,
        },
    )


def _create_support_tables() -> None:
    op.create_table(
        'benefit_ege_requirements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'rule_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('benefit_rules.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('min_score', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('rule_id', name='uq_benefit_ege_requirements_rule'),
        sa.CheckConstraint(
            'min_score IS NULL OR (min_score >= 0 AND min_score <= 100)',
            name='ck_benefit_ege_min_score',
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_ege_requirements_rule_id '
        'ON benefit_ege_requirements (rule_id)'
    )

    op.create_table(
        'benefit_rule_migration_issues',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'rule_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('benefit_rules.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column(
            'entity_type', sa.String(), nullable=False,
            server_default='benefit_rule',
        ),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('field', sa.String(), nullable=True),
        sa.Column('raw_value', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column(
            'resolved', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
    )
    for index, column in (
        ('ix_benefit_rule_migration_issues_rule_id', 'rule_id'),
        ('ix_benefit_rule_migration_issues_entity_type', 'entity_type'),
        ('ix_benefit_rule_migration_issues_entity_id', 'entity_id'),
        ('ix_benefit_rule_migration_issues_resolved', 'resolved'),
        ('ix_benefit_rule_migration_issues_createdAt', '"createdAt"'),
    ):
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {index} '
            f'ON benefit_rule_migration_issues ({column})'
        )

    op.create_table(
        'migration_archive',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('field', sa.String(), nullable=True),
        sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
    )
    for index, column in (
        ('ix_migration_archive_entity_type', 'entity_type'),
        ('ix_migration_archive_entity_id', 'entity_id'),
        ('ix_migration_archive_createdAt', '"createdAt"'),
    ):
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {index} '
            f'ON migration_archive ({column})'
        )


def _upgrade_profiles(bind) -> None:
    op.execute('ALTER TABLE season_profiles ADD COLUMN IF NOT EXISTS name varchar')
    op.execute(
        'ALTER TABLE season_profiles ADD COLUMN IF NOT EXISTS name_norm varchar'
    )
    op.execute(
        'ALTER TABLE season_profiles ADD COLUMN IF NOT EXISTS rsosh_level varchar'
    )

    rows = bind.execute(
        sa.text(
            """
            SELECT id, season_id, profile_name, discipline, subject, description
            FROM season_profiles
            ORDER BY "createdAt" NULLS FIRST, id
            """
        )
    ).mappings().all()

    seen = {}
    for row in rows:
        name = next(
            (
                (row[key] or '').strip()
                for key in ('profile_name', 'discipline', 'subject')
                if (row[key] or '').strip()
            ),
            '',
        )
        if not name:
            name = 'Профиль'
            note = 'Название профиля не сохранилось; подставлено «Профиль»'
        else:
            note = None
        norm = _normalize_name(name) or 'профиль'
        key = (row['season_id'], norm)
        if key in seen:
            keep_id = seen[key]
            # Правила переводим на оставшийся профиль: иначе после удаления
            # дубля они потеряли бы привязку (FK ON DELETE SET NULL).
            bind.execute(
                sa.text(
                    'UPDATE benefit_rules SET profile_id = :keep '
                    'WHERE profile_id = :drop'
                ),
                {'keep': keep_id, 'drop': row['id']},
            )
            raw = bind.execute(
                sa.text(
                    'SELECT to_jsonb(p)::text FROM season_profiles p WHERE id = :id'
                ),
                {'id': row['id']},
            ).scalar_one()
            _archive_json(
                bind, 'season_profile', row['id'], 'row', raw,
                'Дубль профиля внутри сезона слит с основным профилем',
            )
            bind.execute(
                sa.text('DELETE FROM season_profiles WHERE id = :id'),
                {'id': row['id']},
            )
            continue

        seen[key] = row['id']
        bind.execute(
            sa.text(
                """
                UPDATE season_profiles
                SET name = :name, name_norm = :norm
                WHERE id = :id
                """
            ),
            {'name': name, 'norm': norm, 'id': row['id']},
        )
        if note:
            _archive_json(
                bind, 'season_profile', row['id'], 'name',
                json.dumps('Профиль'), note
            )

    op.execute(
        'ALTER TABLE season_profiles ALTER COLUMN name SET NOT NULL'
    )
    op.execute(
        'ALTER TABLE season_profiles ALTER COLUMN name_norm SET NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_season_profiles_season_name '
        'ON season_profiles (season_id, name_norm)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_season_profiles_rsosh_level '
        'ON season_profiles (rsosh_level)'
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_season_profiles_rsosh_level'
            ) THEN
                ALTER TABLE season_profiles
                ADD CONSTRAINT ck_season_profiles_rsosh_level
                CHECK (rsosh_level IS NULL OR rsosh_level IN ('1', '2', '3'));
            END IF;
        END $$;
        """
    )

    # Уровень сезона переносится только туда, где он однозначен: сезон с
    # единственным профилем. Иначе значение не описывает ни один профиль.
    seasons = bind.execute(
        sa.text(
            """
            SELECT id, season_label, rsosh_level
            FROM olympiad_seasons
            WHERE rsosh_level IS NOT NULL
            """
        )
    ).mappings().all()
    for season in seasons:
        profiles = bind.execute(
            sa.text('SELECT id, rsosh_level FROM season_profiles WHERE season_id = :id'),
            {'id': season['id']},
        ).mappings().all()
        note = 'Уровень сезона: перенесён в единственный профиль сезона'
        if len(profiles) == 1 and not profiles[0]['rsosh_level']:
            bind.execute(
                sa.text(
                    'UPDATE season_profiles SET rsosh_level = :level WHERE id = :id'
                ),
                {'level': season['rsosh_level'], 'id': profiles[0]['id']},
            )
        elif len(profiles) == 0:
            note = (
                'Уровень сезона не перенесён: в сезоне не было профилей. '
                'Профиль нужно завести вручную.'
            )
        else:
            note = (
                'Уровень сезона не перенесён: профилей несколько, значение '
                'не описывает ни один из них.'
            )
        _archive_json(
            bind,
            'olympiad_season',
            season['id'],
            'rsosh_level',
            json.dumps(str(season['rsosh_level'])),
            note,
        )


def _upgrade_rules(bind) -> None:
    op.execute(
        'ALTER TABLE benefit_rules '
        'ADD COLUMN IF NOT EXISTS needs_review boolean NOT NULL DEFAULT false'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_needs_review '
        'ON benefit_rules (needs_review)'
    )

    # Старые источники → документы. source_id ссылается на sources, у которых
    # уже может быть doc_id; переносим только когда документ принадлежит тому
    # же вузу (или источнику без вуза) и у правила документа ещё нет.
    op.execute(
        """
        UPDATE benefit_rules br
        SET doc_id = s.doc_id
        FROM sources s
        WHERE br.source_id = s.id
          AND br.doc_id IS NULL
          AND s.doc_id IS NOT NULL
          AND (s.university_id IS NULL OR s.university_id = br.university_id)
        """
    )

    rules = bind.execute(
        sa.text(
            """
            SELECT id, university_id, season_id, profile_id, doc_id, source_id,
                   source_url, required_result, required_result_value, subject,
                   additional_requirements
            FROM benefit_rules
            """
        )
    ).mappings().all()

    for rule in rules:
        changed = False

        if not rule['season_id'] or not rule['profile_id']:
            changed = True

        raw_result = (rule['required_result'] or '').strip()
        if raw_result and not (rule['required_result_value'] or '').strip():
            mapped = None
            lowered = raw_result.casefold()
            if 'победител' in lowered and 'приз' in lowered:
                mapped = 'WINNER_OR_PRIZE'
            elif 'победител' in lowered:
                mapped = 'WINNER'
            elif 'приз' in lowered:
                mapped = 'PRIZE'
            mapped = _RESULT_ALIASES.get(lowered, mapped)
            if mapped:
                bind.execute(
                    sa.text(
                        'UPDATE benefit_rules '
                        'SET required_result_type = COALESCE(required_result_type, :t) '
                        'WHERE id = :id'
                    ),
                    {'t': mapped, 'id': rule['id']},
                )
            else:
                _issue(
                    bind, rule['id'], 'required_result', raw_result,
                    'Свободный текст результата не удалось однозначно '
                    'преобразовать в тип результата',
                )
                changed = True

        if (rule['required_result_value'] or '').strip():
            _archive_json(
                bind, 'benefit_rule', rule['id'], 'required_result_value',
                json.dumps(str(rule['required_result_value'])),
                'Свободное значение результата сохранено для ручной проверки',
            )
            _issue(
                bind, rule['id'], 'required_result_value',
                rule['required_result_value'],
                'Свободное значение результата требует ручного переноса',
            )
            changed = True

        if (rule['subject'] or '').strip():
            _archive_json(
                bind, 'benefit_rule', rule['id'], 'subject',
                json.dumps(str(rule['subject'])),
                'Предмет/профиль правила больше не хранится в правиле',
            )
            _issue(
                bind, rule['id'], 'subject', rule['subject'],
                'Предмет из правила нужно перенести в профиль сезона или '
                'требование ЕГЭ',
            )
            changed = True

        additional = (rule['additional_requirements'] or '').strip()
        if additional:
            match = _EGE_RE.match(additional)
            subject = None
            min_score = None
            if match:
                subject = _clean_subject(match.group('subject'))
                try:
                    score = int(match.group('score'))
                except (TypeError, ValueError):
                    score = None
                if score is not None and 0 <= score <= 100:
                    min_score = score
            if not subject:
                match = _EGE_SUBJECT_RE.match(additional)
                if match:
                    subject = _clean_subject(match.group('subject'))
            if subject:
                exists = bind.execute(
                    sa.text(
                        'SELECT 1 FROM benefit_ege_requirements WHERE rule_id = :id'
                    ),
                    {'id': rule['id']},
                ).scalar_one_or_none()
                if not exists:
                    bind.execute(
                        sa.text(
                            """
                            INSERT INTO benefit_ege_requirements
                                (id, rule_id, subject, min_score, "createdAt",
                                 "updatedAt")
                            VALUES
                                (:id, :rule_id, :subject, :min_score, now(), now())
                            """
                        ),
                        {
                            'id': uuid.uuid4(),
                            'rule_id': rule['id'],
                            'subject': subject,
                            'min_score': min_score,
                        },
                    )
            else:
                _issue(
                    bind, rule['id'], 'additional_requirements', additional,
                    'Дополнительные требования не разобраны автоматически',
                )
                changed = True
            _archive_json(
                bind, 'benefit_rule', rule['id'], 'additional_requirements',
                json.dumps(additional),
                'Исходный текст дополнительных требований',
            )

        if (rule['source_url'] or '').strip() and not rule['doc_id']:
            _issue(
                bind, rule['id'], 'source_url', rule['source_url'],
                'Ссылка на источник не привязана к документу: нужен документ '
                'университета',
            )
            changed = True
        if (rule['source_url'] or '').strip():
            _archive_json(
                bind, 'benefit_rule', rule['id'], 'source_url',
                json.dumps(str(rule['source_url'])),
                'Ссылка на источник перенесена в архив',
            )

        if changed:
            bind.execute(
                sa.text(
                    'UPDATE benefit_rules SET needs_review = true WHERE id = :id'
                ),
                {'id': rule['id']},
            )

    # Правила без сезона/профиля — исторические: они остаются, но попадают в
    # очередь ручного заполнения, а не в «полноценный» каталог.
    op.execute(
        """
        UPDATE benefit_rules
        SET needs_review = true
        WHERE season_id IS NULL OR profile_id IS NULL
        """
    )


def _add_rule_constraints() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_benefit_rules_result_type'
            ) THEN
                ALTER TABLE benefit_rules
                ADD CONSTRAINT ck_benefit_rules_result_type
                CHECK (
                    required_result_type IS NULL
                    OR required_result_type IN ('WINNER', 'PRIZE', 'WINNER_OR_PRIZE')
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_docs_type'
            ) THEN
                ALTER TABLE docs
                ADD CONSTRAINT ck_docs_type
                CHECK (type IN ('RSOSH_LIST', 'UNIVERSITY_ORDER', 'OTHER'));
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    _create_support_tables()
    _upgrade_profiles(bind)
    _upgrade_rules(bind)
    _add_rule_constraints()


def downgrade() -> None:
    """Откат только новой схемы; перенесённые данные остаются.

    Удаление аддитивных таблиц и колонок не возвращает старые значения: они
    лежат в ``migration_archive``. Старые колонки ``season_profiles`` и
    ``benefit_rules`` ещё существуют (их удаляет ``0016``), поэтому откат
    возвращает приложение к состоянию после ``0014`` без потери данных.
    """
    op.execute('DROP INDEX IF EXISTS ix_benefit_rules_needs_review')
    op.execute(
        'ALTER TABLE benefit_rules DROP COLUMN IF EXISTS needs_review'
    )
    op.execute(
        'DROP INDEX IF EXISTS uq_season_profiles_season_name'
    )
    op.execute(
        'DROP INDEX IF EXISTS ix_season_profiles_rsosh_level'
    )
    op.execute(
        'ALTER TABLE season_profiles DROP COLUMN IF EXISTS name'
    )
    op.execute(
        'ALTER TABLE season_profiles DROP COLUMN IF EXISTS name_norm'
    )
    op.execute(
        'ALTER TABLE season_profiles DROP COLUMN IF EXISTS rsosh_level'
    )
    op.execute('DROP TABLE IF EXISTS benefit_ege_requirements')
    op.execute('DROP TABLE IF EXISTS benefit_rule_migration_issues')
    op.execute('DROP TABLE IF EXISTS migration_archive')
    op.execute(
        'ALTER TABLE benefit_rules DROP CONSTRAINT IF EXISTS ck_benefit_rules_result_type'
    )
    op.execute('ALTER TABLE docs DROP CONSTRAINT IF EXISTS ck_docs_type')
