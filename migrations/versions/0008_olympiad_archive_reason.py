"""Причина архивирования олимпиады.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27

Статус ``ARCHIVED`` означает «олимпиады нет в актуальном перечне РСОШ», но
причину архивирования определяют два разных механизма:

- импорт РСОШ — олимпиада пропала из перечня (``RSOSH_ABSENT``); вернуть её в
  актуальные должен следующий импорт, где она снова встретится;
- администратор — олимпиада исключена из каталога руками, например из-за
  ошибки в данных (``MANUAL``); такую запись можно вернуть вручную.

Без сохранения причины ручное «вернуть» превращало бы олимпиаду в актуальную
по перечню РСОШ только потому, что нажали кнопку.

Существующие архивные записи получают причину по их источнику: олимпиады из
документа РСОШ считаются архивированными по перечню, остальные — вручную.
"""

import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('olympiads', sa.Column('archive_reason', sa.String(), nullable=True))
    op.execute(
        "UPDATE olympiads SET archive_reason = 'RSOSH_ABSENT' "
        "WHERE status = 'ARCHIVED' AND source_doc_id IS NOT NULL"
    )
    op.execute(
        "UPDATE olympiads SET archive_reason = 'MANUAL' "
        "WHERE status = 'ARCHIVED' AND source_doc_id IS NULL"
    )


def downgrade() -> None:
    op.drop_column('olympiads', 'archive_reason')
