"""notifications 表 + 评论 mentioned_user_ids

Revision ID: 016
Revises: 015
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "notifications" not in tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        op.create_index("ix_notifications_type", "notifications", ["type"])

    if "canvas_comment_messages" in tables:
        cols = {c["name"] for c in insp.get_columns("canvas_comment_messages")}
        if "mentioned_user_ids" not in cols:
            op.add_column(
                "canvas_comment_messages",
                sa.Column("mentioned_user_ids", sa.Text(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_comment_messages" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("canvas_comment_messages")}
        if "mentioned_user_ids" in cols:
            op.drop_column("canvas_comment_messages", "mentioned_user_ids")
    if "notifications" in insp.get_table_names():
        op.drop_table("notifications")
