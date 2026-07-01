"""agent_conversations table

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "agent_conversations" in insp.get_table_names():
        return
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("messages", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_agent_conv_project_user"),
    )
    op.create_index("ix_agent_conversations_project_id", "agent_conversations", ["project_id"])
    op.create_index("ix_agent_conversations_user_id", "agent_conversations", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "agent_conversations" not in insp.get_table_names():
        return
    op.drop_index("ix_agent_conversations_user_id", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_project_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
