"""tasks rating + prompt trace fields

Revision ID: 028
Revises: 027
"""

from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

_NEW_COLUMNS = (
    ("user_rating", sa.Integer(), None),
    ("rating_tags", sa.Text(), None),
    ("rated_at", sa.DateTime(timezone=True), None),
    ("original_input", sa.Text(), None),
    ("compiled_prompt", sa.Text(), None),
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
