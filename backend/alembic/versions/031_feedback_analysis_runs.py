"""feedback analysis run history

Revision ID: 031
Revises: 030
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "feedback_analysis_runs" not in insp.get_table_names():
        op.create_table(
            "feedback_analysis_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("vision_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("analysis_text", sa.Text(), nullable=False),
            sa.Column("analysis_json", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index(
            "ix_feedback_analysis_runs_created_by",
            "feedback_analysis_runs",
            ["created_by"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "feedback_analysis_runs" in insp.get_table_names():
        op.drop_index("ix_feedback_analysis_runs_created_by", table_name="feedback_analysis_runs")
        op.drop_table("feedback_analysis_runs")
