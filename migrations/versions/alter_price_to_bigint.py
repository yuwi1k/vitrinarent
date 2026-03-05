"""
Change properties.price from Integer to BigInteger.

Revision ID: alter_price_to_bigint
Revises: add_sort_order
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "alter_price_to_bigint"
down_revision: Union[str, None] = "add_cian_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "properties",
        "price",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "properties",
        "price",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )

