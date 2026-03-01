"""add avito_object_type to properties

Revision ID: add_avito_obj
Revises: add_sort_order
Create Date: add avito_object_type for feed

"""
from alembic import op
import sqlalchemy as sa


revision = "add_avito_obj"
down_revision = "add_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("avito_object_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "avito_object_type")
