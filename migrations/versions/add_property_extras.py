"""add extra characteristics to properties

Revision ID: add_property_extras
Revises: add_avito_data
Create Date: 2026-03-03

"""
from alembic import op
import sqlalchemy as sa


revision = "add_property_extras"
down_revision = "add_avito_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("floors_total", sa.Integer(), nullable=True))
    op.add_column("properties", sa.Column("floor_number", sa.Integer(), nullable=True))
    op.add_column("properties", sa.Column("power_kw", sa.Float(), nullable=True))
    op.add_column("properties", sa.Column("ceiling_height", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "ceiling_height")
    op.drop_column("properties", "power_kw")
    op.drop_column("properties", "floor_number")
    op.drop_column("properties", "floors_total")

