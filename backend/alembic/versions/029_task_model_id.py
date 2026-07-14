"""tasks model_id field

Revision ID: 029
Revises: 028
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "model_id" not in cols:
        op.add_column("tasks", sa.Column("model_id", sa.String(length=64), nullable=True))
        op.create_index("ix_tasks_model_id", "tasks", ["model_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "model_id" in cols:
        op.drop_index("ix_tasks_model_id", table_name="tasks")
        op.drop_column("tasks", "model_id")
