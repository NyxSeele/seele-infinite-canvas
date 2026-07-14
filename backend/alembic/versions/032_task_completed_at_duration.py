"""tasks completed_at + generation_seconds

Revision ID: 032
Revises: 031
"""

from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "completed_at" not in cols:
        op.add_column(
            "tasks",
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "generation_seconds" not in cols:
        op.add_column(
            "tasks",
            sa.Column("generation_seconds", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "generation_seconds" in cols:
        op.drop_column("tasks", "generation_seconds")
    if "completed_at" in cols:
        op.drop_column("tasks", "completed_at")
