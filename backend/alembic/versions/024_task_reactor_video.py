"""tasks.use_reactor + reactor_face_image (G45)

Revision ID: 024
Revises: 023
"""

from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "use_reactor" not in cols:
        op.add_column(
            "tasks",
            sa.Column("use_reactor", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "reactor_face_image" not in cols:
        op.add_column("tasks", sa.Column("reactor_face_image", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "reactor_face_image" in cols:
        op.drop_column("tasks", "reactor_face_image")
    if "use_reactor" in cols:
        op.drop_column("tasks", "use_reactor")
