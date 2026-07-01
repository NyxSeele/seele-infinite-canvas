"""teams, team_id on projects/assets/tasks, canvas version

Revision ID: 007
Revises: 006
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id"),
    )
    op.create_index("ix_teams_owner_id", "teams", ["owner_id"], unique=True)

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])

    with op.batch_alter_table("canvas_projects") as batch:
        batch.add_column(sa.Column("team_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
        batch.create_foreign_key(
            "fk_canvas_projects_team_id", "teams", ["team_id"], ["id"]
        )
        batch.create_index("ix_canvas_projects_team_id", ["team_id"])

    with op.batch_alter_table("user_assets") as batch:
        batch.add_column(sa.Column("team_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_user_assets_team_id", "teams", ["team_id"], ["id"]
        )
        batch.create_index("ix_user_assets_team_id", ["team_id"])

    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("team_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_tasks_team_id", "teams", ["team_id"], ["id"])
        batch.create_index("ix_tasks_team_id", ["team_id"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_team_id")
        batch.drop_constraint("fk_tasks_team_id", type_="foreignkey")
        batch.drop_column("team_id")

    with op.batch_alter_table("user_assets") as batch:
        batch.drop_index("ix_user_assets_team_id")
        batch.drop_constraint("fk_user_assets_team_id", type_="foreignkey")
        batch.drop_column("team_id")

    with op.batch_alter_table("canvas_projects") as batch:
        batch.drop_index("ix_canvas_projects_team_id")
        batch.drop_constraint("fk_canvas_projects_team_id", type_="foreignkey")
        batch.drop_column("version")
        batch.drop_column("team_id")

    op.drop_index("ix_team_members_user_id", table_name="team_members")
    op.drop_index("ix_team_members_team_id", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_teams_owner_id", table_name="teams")
    op.drop_table("teams")
