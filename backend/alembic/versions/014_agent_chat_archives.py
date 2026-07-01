"""agent_chat_archives table

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "agent_chat_archives" in insp.get_table_names():
        return
    op.create_table(
        "agent_chat_archives",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="未命名对话"),
        sa.Column("messages", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_chat_archives_project_id", "agent_chat_archives", ["project_id"]
    )
    op.create_index("ix_agent_chat_archives_user_id", "agent_chat_archives", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "agent_chat_archives" not in insp.get_table_names():
        return
    op.drop_index("ix_agent_chat_archives_user_id", table_name="agent_chat_archives")
    op.drop_index("ix_agent_chat_archives_project_id", table_name="agent_chat_archives")
    op.drop_table("agent_chat_archives")
