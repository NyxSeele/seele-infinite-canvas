"""tasks feedback enrichment fields

Revision ID: 030
Revises: 029
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None

_NEW_COLUMNS = (
    ("rating_comment", sa.Text(), None),
    ("generation_params", sa.Text(), None),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    for name, col_type, _ in _NEW_COLUMNS:
        if name not in cols:
            op.add_column("tasks", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    for name, _, _ in reversed(_NEW_COLUMNS):
        if name in cols:
            op.drop_column("tasks", name)
