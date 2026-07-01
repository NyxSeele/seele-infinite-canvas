"""task prompt_text and nullable user_id

Revision ID: 002
Revises: 001
Create Date: 2026-05-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tasks" not in inspector.get_table_names():
        return

    cols = {c["name"]: c for c in inspector.get_columns("tasks")}
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        if "prompt_text" not in cols:
            batch_op.add_column(sa.Column("prompt_text", sa.Text(), nullable=True))
        user_col = cols.get("user_id")
        if user_col is not None and user_col.get("nullable") is False:
            batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tasks" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("tasks")}
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        if "user_id" in cols:
            batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        if "prompt_text" in cols:
            batch_op.drop_column("prompt_text")
