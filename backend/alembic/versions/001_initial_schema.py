"""initial user and quota schema

Revision ID: 001
Revises:
Create Date: 2026-05-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("username", sa.String(length=20), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"])
        op.create_index("ix_users_username", "users", ["username"])

    if "quota_plans" not in tables:
        op.create_table(
            "quota_plans",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=50), nullable=False),
            sa.Column("image_limit", sa.Integer(), nullable=False),
            sa.Column("video_limit", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "user_quotas" not in tables:
        op.create_table(
            "user_quotas",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("plan_name", sa.String(length=50), nullable=False),
            sa.Column("image_limit", sa.Integer(), nullable=False),
            sa.Column("video_limit", sa.Integer(), nullable=False),
            sa.Column("image_used", sa.Integer(), nullable=False),
            sa.Column("video_used", sa.Integer(), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_user_quotas_user_id"),
        )
        op.create_index("ix_user_quotas_user_id", "user_quotas", ["user_id"])

    if "tasks" not in tables:
        op.create_table(
            "tasks",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("task_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tasks_user_id", "tasks", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "tasks" in tables:
        op.drop_index("ix_tasks_user_id", table_name="tasks")
        op.drop_table("tasks")
    if "user_quotas" in tables:
        op.drop_index("ix_user_quotas_user_id", table_name="user_quotas")
        op.drop_table("user_quotas")
    if "quota_plans" in tables:
        op.drop_table("quota_plans")
    if "users" in tables:
        op.drop_index("ix_users_username", table_name="users")
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
