"""add sort_order to property_images

Revision ID: add_sort_order
Revises: 1c244b3d39e1
Create Date: add sort_order column for gallery order

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_sort_order"
down_revision = "1c244b3d39e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("property_images", sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")))
    # backfill: set sort_order = id so existing rows keep stable order
    op.execute(sa.text("UPDATE property_images SET sort_order = id"))


def downgrade() -> None:
    op.drop_column("property_images", "sort_order")
