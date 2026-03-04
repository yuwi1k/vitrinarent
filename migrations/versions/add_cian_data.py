"""add cian_data JSON to properties

Revision ID: add_cian_data
Revises: add_property_extras
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa


revision = "add_cian_data"
down_revision = "add_property_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("cian_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "cian_data")
