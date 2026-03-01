"""add avito_data JSON to properties

Revision ID: add_avito_data
Revises: add_avito_obj
Create Date: add avito_data for Avito template fields

"""
from alembic import op
import sqlalchemy as sa


revision = "add_avito_data"
down_revision = "add_avito_obj"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("avito_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "avito_data")
