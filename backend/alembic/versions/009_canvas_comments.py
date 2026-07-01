"""canvas comment threads and messages

Revision ID: 009
Revises: 008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "canvas_comment_threads" in inspector.get_table_names():
        return

    op.create_table(
        "canvas_comment_threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["canvas_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "node_id", name="uq_canvas_comment_thread_node"),
    )
    op.create_index(
        "ix_canvas_comment_threads_project_id",
        "canvas_comment_threads",
        ["project_id"],
    )
    op.create_index(
        "ix_canvas_comment_threads_node_id",
        "canvas_comment_threads",
        ["node_id"],
    )

    op.create_table(
        "canvas_comment_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("author_name", sa.String(length=128), nullable=False),
        sa.Column("body", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["canvas_comment_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canvas_comment_messages_thread_id",
        "canvas_comment_messages",
        ["thread_id"],
    )


def downgrade() -> None:
    op.drop_table("canvas_comment_messages")
    op.drop_table("canvas_comment_threads")
