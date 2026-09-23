"""Drop the legacy events table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23

Историческая таблица ``events`` больше не используется: каталог олимпиад
перенесён в ``olympiads`` (миграция 0004), события исключены из приложения.
Свежие базы с нуля создаются без этой таблицы (0001), поэтому здесь она
удаляется только у существующих инсталляций.

Индекс-констрейнты упоминаются намеренно: ``DROP ... IF EXISTS`` делает
миграцию идемпотентной и безопасной как для чистых, так и для старых баз.
"""

from alembic import op

# Названия миграции (идентификаторы ревизий)
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Удалить события и их индексы (если они ещё существуют)."""
    op.execute('DROP INDEX IF EXISTS ix_events_owner')
    op.execute('DROP INDEX IF EXISTS ix_events_createdAt')
    op.execute('DROP TABLE IF EXISTS events')


def downgrade() -> None:
    """Восстановить таблицу events (без данных) для отката."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id UUID PRIMARY KEY,
            owner UUID,
            name VARCHAR,
            disc VARCHAR,
            preview_picture VARCHAR,
            picture VARCHAR,
            "isActive" BOOLEAN,
            "createdAt" TIMESTAMPTZ,
            "updatedAt" TIMESTAMPTZ
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_events_owner ON events (owner)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_events_createdAt ON events ("createdAt")'
    )