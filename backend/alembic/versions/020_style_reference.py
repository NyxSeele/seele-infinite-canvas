"""canvas_projects style_reference JSON column

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "style_reference" not in cols:
        op.add_column("canvas_projects", sa.Column("style_reference", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "style_reference" in cols:
        op.drop_column("canvas_projects", "style_reference")
