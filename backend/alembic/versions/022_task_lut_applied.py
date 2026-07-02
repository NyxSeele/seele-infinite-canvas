"""tasks.lut_applied column

Revision ID: 022
Revises: 021
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "lut_applied" not in cols:
        op.add_column(
            "tasks",
            sa.Column("lut_applied", sa.Boolean(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "lut_applied" in cols:
        op.drop_column("tasks", "lut_applied")
