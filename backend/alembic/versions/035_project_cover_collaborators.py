"""project cover columns and project_collaborators

Revision ID: 035
Revises: 034
"""

from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("canvas_projects")}
    if "cover_url" not in cols:
        op.add_column("canvas_projects", sa.Column("cover_url", sa.String(length=1024), nullable=True))
    if "cover_media_type" not in cols:
        op.add_column("canvas_projects", sa.Column("cover_media_type", sa.String(length=16), nullable=True))

    if "project_collaborators" not in insp.get_table_names():
        op.create_table(
            "project_collaborators",
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("canvas_projects.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index(
            "ix_project_collaborators_project_last_active",
            "project_collaborators",
            ["project_id", "last_active_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "project_collaborators" in insp.get_table_names():
        indexes = {i["name"] for i in insp.get_indexes("project_collaborators")}
        if "ix_project_collaborators_project_last_active" in indexes:
            op.drop_index("ix_project_collaborators_project_last_active", table_name="project_collaborators")
        op.drop_table("project_collaborators")

    if "canvas_projects" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("canvas_projects")}
        if "cover_media_type" in cols:
            op.drop_column("canvas_projects", "cover_media_type")
        if "cover_url" in cols:
            op.drop_column("canvas_projects", "cover_url")
