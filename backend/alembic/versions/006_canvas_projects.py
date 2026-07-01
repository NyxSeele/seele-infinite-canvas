"""canvas projects multi-project support

Revision ID: 006
Revises: 005
Create Date: 2026-06-09

"""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "canvas_projects" not in tables:
        op.create_table(
            "canvas_projects",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_canvas_projects_user_id", "canvas_projects", ["user_id"])

    if "canvas_states" in tables:
        rows = bind.execute(
            sa.text("SELECT user_id, data, updated_at FROM canvas_states")
        ).fetchall()
        for row in rows:
            user_id, data, updated_at = row[0], row[1], row[2]
            exists = bind.execute(
                sa.text("SELECT 1 FROM canvas_projects WHERE user_id = :uid LIMIT 1"),
                {"uid": user_id},
            ).first()
            if exists:
                continue
            payload = data or '{"nodes":[],"edges":[]}'
            try:
                parsed = json.loads(payload)
                name = (parsed.get("project_name") or "未命名画布").strip()[:256]
            except Exception:
                name = "未命名画布"
            bind.execute(
                sa.text(
                    """
                    INSERT INTO canvas_projects (id, user_id, name, data, created_at, updated_at)
                    VALUES (:id, :user_id, :name, :data, :created_at, :updated_at)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "name": name or "未命名画布",
                    "data": payload,
                    "created_at": updated_at,
                    "updated_at": updated_at,
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "canvas_projects" in tables:
        op.drop_index("ix_canvas_projects_user_id", table_name="canvas_projects")
        op.drop_table("canvas_projects")
