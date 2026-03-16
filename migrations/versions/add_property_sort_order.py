"""Add sort_order column to properties for manual catalog ordering.

Revision ID: add_property_sort_order
Revises: add_publish_on_flags
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa


revision = "add_property_sort_order"
down_revision = "add_publish_on_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_properties_sort_order", "properties", ["sort_order"])


def downgrade() -> None:
    op.drop_index("ix_properties_sort_order", table_name="properties")
    op.drop_column("properties", "sort_order")
