"""team assets flag and canvas shares

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_assets" in tables:
        cols = {c["name"] for c in inspector.get_columns("user_assets")}
        if "is_team" not in cols:
            op.add_column(
                "user_assets",
                sa.Column("is_team", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    if "canvas_shares" not in tables:
        op.create_table(
            "canvas_shares",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_name", sa.String(length=256), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_canvas_shares_user_id", "canvas_shares", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "canvas_shares" in tables:
        op.drop_index("ix_canvas_shares_user_id", table_name="canvas_shares")
        op.drop_table("canvas_shares")

    if "user_assets" in tables:
        cols = {c["name"] for c in inspector.get_columns("user_assets")}
        if "is_team" in cols:
            op.drop_column("user_assets", "is_team")
