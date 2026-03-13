"""add publish_on_avito and publish_on_cian flags to properties

Revision ID: add_publish_on_flags
Revises: add_unified_fields
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa


revision = "add_publish_on_flags"
down_revision = "add_unified_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("publish_on_avito", sa.Boolean(), server_default="true", nullable=True))
    op.add_column("properties", sa.Column("publish_on_cian", sa.Boolean(), server_default="true", nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "publish_on_cian")
    op.drop_column("properties", "publish_on_avito")
