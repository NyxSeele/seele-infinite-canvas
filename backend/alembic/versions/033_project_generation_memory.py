"""canvas_projects generation_memory JSON column

Revision ID: 033
Revises: 032
"""

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "generation_memory" not in cols:
        op.add_column(
            "canvas_projects",
            sa.Column("generation_memory", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "generation_memory" in cols:
        op.drop_column("canvas_projects", "generation_memory")
