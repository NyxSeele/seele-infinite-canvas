"""team invite links

Revision ID: 010
Revises: 009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "team_invites" in inspector.get_table_names():
        return

    op.create_table(
        "team_invites",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index("ix_team_invites_team_id", "team_invites", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_team_invites_team_id", table_name="team_invites")
    op.drop_table("team_invites")
