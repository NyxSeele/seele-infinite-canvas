"""review_videos + review_comments (video review feature)

Revision ID: 026
Revises: 025
"""

from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "review_videos" not in tables:
        op.create_table(
            "review_videos",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("video_url", sa.String(length=1024), nullable=False),
            sa.Column("thumbnail_url", sa.String(length=1024), nullable=True),
            sa.Column(
                "publisher_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("publisher_name", sa.String(length=64), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        op.create_index("ix_review_videos_publisher_id", "review_videos", ["publisher_id"])
        op.create_index("ix_review_videos_published_at", "review_videos", ["published_at"])
        op.create_index("ix_review_videos_is_active", "review_videos", ["is_active"])

    if "review_comments" not in tables:
        op.create_table(
            "review_comments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "video_id",
                sa.Integer(),
                sa.ForeignKey("review_videos.id"),
                nullable=False,
            ),
            sa.Column("reviewer_name", sa.String(length=64), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("liked", sa.Boolean(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_review_comments_video_id", "review_comments", ["video_id"])
        op.create_index("ix_review_comments_created_at", "review_comments", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "review_comments" in tables:
        op.drop_index("ix_review_comments_created_at", table_name="review_comments")
        op.drop_index("ix_review_comments_video_id", table_name="review_comments")
        op.drop_table("review_comments")

    if "review_videos" in tables:
        op.drop_index("ix_review_videos_is_active", table_name="review_videos")
        op.drop_index("ix_review_videos_published_at", table_name="review_videos")
        op.drop_index("ix_review_videos_publisher_id", table_name="review_videos")
        op.drop_table("review_videos")
