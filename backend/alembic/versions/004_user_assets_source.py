"""user assets source canvas fields

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_assets" not in inspector.get_table_names():
        op.create_table(
            "user_assets",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("image_url", sa.String(length=1024), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("source_canvas_id", sa.String(length=64), nullable=True),
            sa.Column("source_canvas_name", sa.String(length=256), nullable=True),
            sa.Column("source_node_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_assets_user_id", "user_assets", ["user_id"])
        op.create_index("ix_user_assets_kind", "user_assets", ["kind"])
        op.create_index(
            "ix_user_assets_source_canvas_id", "user_assets", ["source_canvas_id"]
        )
        return

    cols = {c["name"] for c in inspector.get_columns("user_assets")}
    if "source_canvas_id" not in cols:
        op.add_column(
            "user_assets", sa.Column("source_canvas_id", sa.String(length=64), nullable=True)
        )
        op.create_index(
            "ix_user_assets_source_canvas_id", "user_assets", ["source_canvas_id"]
        )
    if "source_canvas_name" not in cols:
        op.add_column(
            "user_assets",
            sa.Column("source_canvas_name", sa.String(length=256), nullable=True),
        )
    if "source_node_id" not in cols:
        op.add_column(
            "user_assets", sa.Column("source_node_id", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_assets" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_assets")}
    if "source_node_id" in cols:
        op.drop_column("user_assets", "source_node_id")
    if "source_canvas_name" in cols:
        op.drop_column("user_assets", "source_canvas_name")
    if "source_canvas_id" in cols:
        op.drop_index("ix_user_assets_source_canvas_id", table_name="user_assets")
        op.drop_column("user_assets", "source_canvas_id")
