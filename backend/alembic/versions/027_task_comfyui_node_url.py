"""tasks.comfyui_node_url — 绑定 ComfyUI 实例 URL

Revision ID: 027
Revises: 026
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "comfyui_node_url" not in cols:
        op.add_column(
            "tasks",
            sa.Column("comfyui_node_url", sa.String(length=256), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "comfyui_node_url" in cols:
        op.drop_column("tasks", "comfyui_node_url")
