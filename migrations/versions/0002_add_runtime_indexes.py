"""Add runtime indexes for users and events.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17

Индексы для часто используемых сортировок и фильтров списков:
- users.createdAt (сортировка списков пользователей);
- events.owner (выборка «мои события», список владельца);
- events.createdAt (сортировка каталога событий).

Вынесены из 0001, чтобы уже существующие базы (созданные через
Base.metadata.create_all), после заклеймления на 0001, получили эти индексы
обычным ``alembic upgrade head``. ``CREATE INDEX IF NOT EXISTS`` делает
миграцию идемпотентной.
"""

from alembic import op

# Названия миграции (идентификаторы ревизий)
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать индекс (если его ещё нет) для каждой горячей колонки."""
    op.execute('CREATE INDEX IF NOT EXISTS ix_users_createdAt ON users ("createdAt")')
    op.execute('CREATE INDEX IF NOT EXISTS ix_events_owner ON events (owner)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_events_createdAt ON events ("createdAt")')


def downgrade() -> None:
    """Удалить индексы."""
    op.execute('DROP INDEX IF EXISTS ix_users_createdAt')
    op.execute('DROP INDEX IF EXISTS ix_events_owner')
    op.execute('DROP INDEX IF EXISTS ix_events_createdAt')