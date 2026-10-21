"""Происхождение связи БВИ: документ-источник и распознанные поля.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19

Связь ``university_olympiads`` раньше хранила только пару (университет,
олимпиада), статус и участников решения. Это достаточно для заявки
представителя, но мало для связи, распознанной из приказа вуза
(``UNIVERSITY_ORDER``): по такой записи нужно видеть, из какого документа она
взята (``source_doc_id``) и с какими дополнительными характеристиками строка
была в приказе (``source_meta`` — направление, профиль, предмет, уровень,
диплом, сезон).

Обе колонки добавляются аддитивно и необязательны: существующие связи
представителей остаются без изменений (``NULL``), а инвариант «связь ссылается
на существующую олимпиаду каталога» сохраняется. Удаление документа-источника
не должно уносить связь: ``source_doc_id`` обнуляется (``ON DELETE SET NULL``),
как и у ``olympiads.source_doc_id``.
"""

from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE university_olympiads '
        'ADD COLUMN IF NOT EXISTS source_doc_id UUID'
    )
    op.execute(
        'ALTER TABLE university_olympiads '
        'ADD COLUMN IF NOT EXISTS source_meta JSONB'
    )
    # Внешний ключ создаётся отдельной командой идемпотентно: повторный накат
    # (или база, где связь уже заведена вручную) не должен падать.
    op.execute(
        'DO $$ BEGIN '
        'ALTER TABLE university_olympiads '
        'ADD CONSTRAINT fk_university_olympiads_source_doc '
        'FOREIGN KEY (source_doc_id) REFERENCES docs (id) '
        'ON DELETE SET NULL; '
        'EXCEPTION WHEN duplicate_object THEN NULL; '
        'END $$'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE university_olympiads '
        'DROP CONSTRAINT IF EXISTS fk_university_olympiads_source_doc'
    )
    op.execute(
        'ALTER TABLE university_olympiads DROP COLUMN IF EXISTS source_meta'
    )
    op.execute(
        'ALTER TABLE university_olympiads DROP COLUMN IF EXISTS source_doc_id'
    )
