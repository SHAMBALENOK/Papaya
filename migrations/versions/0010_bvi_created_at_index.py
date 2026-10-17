"""Индекс на дату создания заявки БВИ.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-15

Очередь модерации читается с сортировкой ``ORDER BY "createdAt", id``
(см. ``app.database.bvi.list_links_enriched``). Без индекса такая сортировка
требует полного прохода и сортировки таблицы, и очередь замедляется линейно
с ростом числа связей. ``CREATE INDEX IF NOT EXISTS`` делает миграцию
идемпотентной (в т.ч. для баз, где таблица уже создана).
"""

from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_university_olympiads_createdAt '
        'ON university_olympiads ("createdAt")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_university_olympiads_createdAt')
