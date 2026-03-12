"""add unified platform fields and stats_data to properties

Revision ID: add_unified_fields
Revises: add_timestamps
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa


revision = "add_unified_fields"
down_revision = "add_timestamps"
branch_labels = None
depends_on = None


_NEW_COLUMNS = [
    ("building_type", sa.String()),
    ("building_class", sa.String()),
    ("decoration", sa.String()),
    ("parking_type", sa.String()),
    ("entrance_type", sa.String()),
    ("layout_type", sa.String()),
    ("heating_type", sa.String()),
    ("property_rights", sa.String()),
    ("rental_type", sa.String()),
    ("parking_spaces", sa.Integer()),
    ("distance_from_road", sa.String()),
    ("stats_data", sa.JSON()),
]


def upgrade() -> None:
    for col_name, col_type in _NEW_COLUMNS:
        op.add_column("properties", sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    for col_name, _ in reversed(_NEW_COLUMNS):
        op.drop_column("properties", col_name)
