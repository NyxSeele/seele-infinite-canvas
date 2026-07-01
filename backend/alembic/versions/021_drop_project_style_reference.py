"""drop canvas_projects.style_reference (shot-level refactor)

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "style_reference" in cols:
        op.drop_column("canvas_projects", "style_reference")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "canvas_projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "style_reference" not in cols:
        op.add_column("canvas_projects", sa.Column("style_reference", sa.Text(), nullable=True))
