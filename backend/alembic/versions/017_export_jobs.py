"""export_jobs 表

Revision ID: 017
Revises: 016
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "export_jobs" not in tables:
        op.create_table(
            "export_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("canvas_projects.id"),
                nullable=False,
            ),
            sa.Column("script_table_node_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("file_path", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_export_jobs_project_id", "export_jobs", ["project_id"])
        op.create_index("ix_export_jobs_created_by", "export_jobs", ["created_by"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "export_jobs" in insp.get_table_names():
        op.drop_table("export_jobs")
