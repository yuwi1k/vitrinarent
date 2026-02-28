"""add slug to properties

Revision ID: 002
Revises: 001
Create Date: 2025-02-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("slug", sa.String(), nullable=True))
    op.create_index(op.f("ix_properties_slug"), "properties", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_properties_slug"), table_name="properties")
    op.drop_column("properties", "slug")
