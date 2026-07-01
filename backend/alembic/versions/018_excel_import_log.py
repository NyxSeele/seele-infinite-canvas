"""excel_import_log 表

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "excel_import_log" not in tables:
        op.create_table(
            "excel_import_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("canvas_projects.id"),
                nullable=False,
            ),
            sa.Column("sheet_name", sa.String(length=256), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("linked_node_id", sa.String(length=128), nullable=True),
            sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "sheet_name", name="uq_excel_import_project_sheet"),
        )
        op.create_index("ix_excel_import_log_project_id", "excel_import_log", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "excel_import_log" in insp.get_table_names():
        op.drop_table("excel_import_log")
