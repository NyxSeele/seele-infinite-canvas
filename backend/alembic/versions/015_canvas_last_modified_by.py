"""canvas_projects last_modified_by

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "last_modified_by" not in cols:
        op.add_column(
            "canvas_projects",
            sa.Column("last_modified_by", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "last_modified_by" in cols:
        op.drop_column("canvas_projects", "last_modified_by")
