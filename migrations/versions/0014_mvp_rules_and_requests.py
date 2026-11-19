"""MVP: перенос старых связей БВИ в правила льгот и запросы сущностей.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-13

Что делает миграция:

1. Переносит ``university_olympiads`` в канонические ``benefit_rules``.
   Перенос идемпотентен: правило создаётся, только если для пары
   «вуз + олимпиада» ещё нет основного правила БВИ (без сезона и профиля).
   Статус ``CONFIRMED`` **не** превращается в ``verified``: старая связь не
   содержит официального документа вуза, а подтверждение без документа было
   бы выдуманным доверием. Обе стороны (``CONFIRMED`` и ``PENDING``)
   становятся опубликованными непроверенными правилами — MVP показывает их с
   предупреждением «Не проверено Papaya». Исходный статус сохраняется в
   истории статусов и в причине версии.
2. Заводит версию 1 и запись истории для перенесённых правил, чтобы откат и
   аудит работали сразу.
3. Добавляет частичный уникальный индекс: у пары «вуз + олимпиада + тип»
   может быть только одно опубликованное основное правило. Дубли, если они
   успели появиться, снимаются с публикации (не удаляются), история
   сохраняется.
4. Создаёт ``entity_requests`` — очередь запросов представителей на
   отсутствующие олимпиады, сезоны и профили.

Старые таблицы не удаляются: ``university_olympiads`` остаётся доступной для
сверки и отката приложения. Удалять её будет отдельная миграция после
подтверждения, что старый слой больше нигде не используется.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- индекс под фильтры каталога -------------------------------------
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_season_id '
        'ON benefit_rules (season_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_profile_id '
        'ON benefit_rules (profile_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_doc_id '
        'ON benefit_rules (doc_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_benefit_rules_source_id '
        'ON benefit_rules (source_id)'
    )

    # --- перенос старых связей -------------------------------------------
    op.execute(
        """
        INSERT INTO benefit_rules (
            id, university_id, olympiad_id, season_id, profile_id,
            benefit_type, verification_status, is_published, version,
            created_by, updated_by, "createdAt", "updatedAt"
        )
        SELECT
            gen_random_uuid(), uo.university_id, uo.olympiad_id, NULL, NULL,
            'BVI', 'unverified', true, 1,
            uo."createdBy", uo."createdBy",
            COALESCE(uo."createdAt", now()),
            COALESCE(uo."updatedAt", now())
        FROM university_olympiads uo
        WHERE NOT EXISTS (
            SELECT 1 FROM benefit_rules br
            WHERE br.university_id = uo.university_id
              AND br.olympiad_id = uo.olympiad_id
              AND br.benefit_type = 'BVI'
              AND br.season_id IS NULL
              AND br.profile_id IS NULL
        )
        """
    )

    # Версия 1 для любой пары «вуз + олимпиада», у которой правила ещё нет.
    # Условие по version_number делает повторный запуск безопасным.
    op.execute(
        """
        INSERT INTO benefit_rule_versions (
            id, rule_id, version_number, snapshot, changed_fields,
            change_reason, verification_status, source_url, changed_by,
            changed_at
        )
        SELECT
            gen_random_uuid(), br.id, 1,
            jsonb_build_object(
                'id', br.id::text,
                'university_id', br.university_id::text,
                'olympiad_id', br.olympiad_id::text,
                'season_id', NULL,
                'profile_id', NULL,
                'benefit_type', br.benefit_type,
                'required_result', br.required_result,
                'required_result_type', br.required_result_type,
                'required_result_value', br.required_result_value,
                'subject', br.subject,
                'additional_requirements', br.additional_requirements,
                'program_ids', '[]'::jsonb,
                'doc_id', NULL,
                'source_id', NULL,
                'source_url', br.source_url,
                'verification_status', br.verification_status,
                'is_published', br.is_published,
                'version', 1
            ),
            '["*"]'::jsonb,
            'migrated from university_olympiads',
            'unverified',
            NULL,
            br.created_by,
            COALESCE(br."createdAt", now())
        FROM university_olympiads uo
        JOIN benefit_rules br
          ON br.university_id = uo.university_id
         AND br.olympiad_id = uo.olympiad_id
         AND br.benefit_type = 'BVI'
         AND br.season_id IS NULL
         AND br.profile_id IS NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM benefit_rule_versions v
            WHERE v.rule_id = br.id AND v.version_number = 1
        )
        """
    )

    # История статусов: исходный статус старой связи остаётся видимым.
    op.execute(
        """
        INSERT INTO benefit_status_history (
            id, rule_id, from_status, to_status, changed_by, changed_at, reason
        )
        SELECT
            gen_random_uuid(), br.id, NULL, 'unverified', br.created_by, now(),
            'migrated from university_olympiads: ' || uo.status
        FROM university_olympiads uo
        JOIN benefit_rules br
          ON br.university_id = uo.university_id
         AND br.olympiad_id = uo.olympiad_id
         AND br.benefit_type = 'BVI'
         AND br.season_id IS NULL
         AND br.profile_id IS NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM benefit_status_history h
            WHERE h.rule_id = br.id
              AND h.reason LIKE 'migrated from university_olympiads:%'
        )
        """
    )

    # --- одно опубликованное основное правило на пару --------------------
    # Дубли не удаляем: снимаем с публикации и оставляем в рабочем списке и
    # истории. Предпочтение — проверенному правилу, затем самому раннему.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY university_id, olympiad_id, benefit_type
                    ORDER BY
                        (verification_status = 'verified') DESC,
                        "createdAt" ASC NULLS FIRST,
                        id
                ) AS rn
            FROM benefit_rules
            WHERE season_id IS NULL
              AND profile_id IS NULL
              AND is_published
        )
        UPDATE benefit_rules br
        SET is_published = false,
            "updatedAt" = now()
        FROM ranked r
        WHERE br.id = r.id AND r.rn > 1
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_benefit_rules_base_published
        ON benefit_rules (university_id, olympiad_id, benefit_type)
        WHERE season_id IS NULL
          AND profile_id IS NULL
          AND is_published
        """
    )

    # --- запросы на отсутствующие сущности -------------------------------
    op.create_table(
        'entity_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'payload',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            'university_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('universities.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'parent_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            'status', sa.String(), nullable=False, server_default='pending'
        ),
        sa.Column(
            'reviewed_by',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'reviewed_at', sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column(
            'created_entity_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            'created_by',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_entity_requests_entity_type '
        'ON entity_requests (entity_type)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_entity_requests_university_id '
        'ON entity_requests (university_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_entity_requests_parent_id '
        'ON entity_requests (parent_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_entity_requests_status '
        'ON entity_requests (status)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_entity_requests_created_by '
        'ON entity_requests (created_by)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_entity_requests_createdAt '
        'ON entity_requests ("createdAt")'
    )


def downgrade() -> None:
    """Откат схемы без удаления перенесённых правил.

    Правила льгот, созданные переносом, остаются: это пользовательские данные
    и история. Удаляется только новая очередь запросов и уникальный индекс —
    без них приложение продолжает работать со старым слоем БВИ.
    """
    op.drop_table('entity_requests')
    op.execute('DROP INDEX IF EXISTS uq_benefit_rules_base_published')
    for index in (
        'ix_benefit_rules_season_id',
        'ix_benefit_rules_profile_id',
        'ix_benefit_rules_doc_id',
        'ix_benefit_rules_source_id',
    ):
        op.execute(f'DROP INDEX IF EXISTS {index}')
