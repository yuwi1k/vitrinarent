"""add telegram_forward_map table

Revision ID: add_telegram_forward_map
Revises: add_cian_data
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa


revision = "add_telegram_forward_map"
down_revision = "add_cian_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_forward_map",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("from_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("forwarded_msg_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_telegram_forward_map_from_chat_id", "telegram_forward_map", ["from_chat_id"])
    op.create_index("ix_telegram_forward_map_forwarded_msg_id", "telegram_forward_map", ["forwarded_msg_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_forward_map_forwarded_msg_id", table_name="telegram_forward_map")
    op.drop_index("ix_telegram_forward_map_from_chat_id", table_name="telegram_forward_map")
    op.drop_table("telegram_forward_map")
