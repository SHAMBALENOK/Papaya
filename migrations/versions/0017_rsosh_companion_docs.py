"""Официальный перечень: типы производных документов XLSX/HTML.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-19

Импорт официального перечня РСОШ сохраняет рядом с исходным PDF две
производные таблицы: ``RSOSH_TABLE`` (XLSX) и ``RSOSH_HTML`` (HTML-версия для
просмотра). Обе записи нужны в ``docs``, чтобы их видели страница документов и
меню импорта; ограничение ``ck_docs_type`` из миграции 0015 их не пропускало.

Тип производного документа нельзя выбрать при загрузке: API принимает только
``RSOSH_LIST``/``UNIVERSITY_ORDER``/``OTHER``, эти значения создаёт сервер.
"""

from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

OLD_TYPES = ('RSOSH_LIST', 'UNIVERSITY_ORDER', 'OTHER')
NEW_TYPES = OLD_TYPES + ('RSOSH_TABLE', 'RSOSH_HTML')


def _types(values) -> str:
    quoted = ', '.join(f"'{value}'" for value in values)
    return f'type IN ({quoted})'


def upgrade() -> None:
    op.execute('ALTER TABLE docs DROP CONSTRAINT IF EXISTS ck_docs_type')
    op.execute(
        f'ALTER TABLE docs ADD CONSTRAINT ck_docs_type CHECK ({_types(NEW_TYPES)})'
    )


def downgrade() -> None:
    # Производные таблицы без этого типа нарушили бы ограничение, поэтому
    # при откате их записи удаляются: восстановить таблицы можно повторным
    # разбором исходного перечня.
    op.execute("DELETE FROM docs WHERE type IN ('RSOSH_TABLE', 'RSOSH_HTML')")
    op.execute('ALTER TABLE docs DROP CONSTRAINT IF EXISTS ck_docs_type')
    op.execute(
        f'ALTER TABLE docs ADD CONSTRAINT ck_docs_type CHECK ({_types(OLD_TYPES)})'
    )
