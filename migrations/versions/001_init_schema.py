"""init schema: properties, property_images, property_documents

Revision ID: 001
Revises:
Create Date: 2025-02-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "properties" not in tables:
        op.create_table(
            "properties",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("price", sa.Integer(), nullable=True),
            sa.Column("area", sa.Float(), nullable=True),
            sa.Column("address", sa.String(), nullable=True),
            sa.Column("main_image", sa.String(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("show_on_main", sa.Boolean(), nullable=True),
            sa.Column("main_page_order", sa.Integer(), nullable=True),
            sa.Column("deal_type", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["properties.id"], ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_properties_id"), "properties", ["id"], unique=False)
        op.create_index(op.f("ix_properties_title"), "properties", ["title"], unique=False)
        op.create_index(op.f("ix_properties_price"), "properties", ["price"], unique=False)
        op.create_index(op.f("ix_properties_area"), "properties", ["area"], unique=False)
        op.create_index(op.f("ix_properties_deal_type"), "properties", ["deal_type"], unique=False)
        op.create_index(op.f("ix_properties_category"), "properties", ["category"], unique=False)

    if "property_images" not in tables:
        op.create_table(
            "property_images",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("image_url", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_property_images_id"), "property_images", ["id"], unique=False)

    if "property_documents" not in tables:
        op.create_table(
            "property_documents",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("document_url", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_property_documents_id"), "property_documents", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_property_documents_id"), table_name="property_documents")
    op.drop_table("property_documents")
    op.drop_index(op.f("ix_property_images_id"), table_name="property_images")
    op.drop_table("property_images")
    op.drop_index(op.f("ix_properties_category"), table_name="properties")
    op.drop_index(op.f("ix_properties_deal_type"), table_name="properties")
    op.drop_index(op.f("ix_properties_area"), table_name="properties")
    op.drop_index(op.f("ix_properties_price"), table_name="properties")
    op.drop_index(op.f("ix_properties_title"), table_name="properties")
    op.drop_index(op.f("ix_properties_id"), table_name="properties")
    op.drop_table("properties")
