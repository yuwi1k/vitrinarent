"""add created_at / updated_at to properties

Revision ID: add_timestamps
Revises: add_cian_data
Create Date: 2026-03-10

"""
from alembic import op
import sqlalchemy as sa


revision = "add_timestamps"
down_revision = "alter_price_to_bigint"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("properties", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE properties SET created_at = NOW(), updated_at = NOW() WHERE created_at IS NULL"))


def downgrade():
    op.drop_column("properties", "updated_at")
    op.drop_column("properties", "created_at")
