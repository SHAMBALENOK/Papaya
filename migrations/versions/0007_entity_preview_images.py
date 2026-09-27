"""Превью-картинки каталога.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-27

У сущностей каталога теперь две картинки:

- ``preview_image`` — маленькая, для карточек каталога;
- ``image`` — большая, для страницы сущности.

Раньше было одно поле ``image``, и его приходилось уменьшать для карточек.
Миграция добавляет ``preview_image`` в ``universities`` и ``olympiads`` и
переносит существующие значения в новое поле, чтобы карточки не стали пустыми:
старое ``image`` остаётся большим изображением страницы, его копия попадает в
превью. Если поле уже было заполнено, оно не перезаписывается.
"""

import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('universities', sa.Column('preview_image', sa.String(), nullable=True))
    op.add_column('olympiads', sa.Column('preview_image', sa.String(), nullable=True))

    op.execute(
        'UPDATE universities SET preview_image = image '
        "WHERE (preview_image IS NULL OR preview_image = '') AND image IS NOT NULL"
    )
    op.execute(
        'UPDATE olympiads SET preview_image = image '
        "WHERE (preview_image IS NULL OR preview_image = '') AND image IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('olympiads', 'preview_image')
    op.drop_column('universities', 'preview_image')
