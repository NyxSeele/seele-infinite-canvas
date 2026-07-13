"""tasks.sound_note + video_backend columns (G39)

Revision ID: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "sound_note" not in cols:
        op.add_column("tasks", sa.Column("sound_note", sa.Text(), nullable=True))
    if "video_backend" not in cols:
        op.add_column(
            "tasks",
            sa.Column("video_backend", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "video_backend" in cols:
        op.drop_column("tasks", "video_backend")
    if "sound_note" in cols:
        op.drop_column("tasks", "sound_note")
