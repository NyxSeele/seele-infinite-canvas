"""drop legacy is_team column on user_assets

Revision ID: 008
Revises: 007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_assets" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_assets")}
    if "team_id" in cols and "is_team" in cols:
        # 旧 is_team 资产挂到用户拥有的团队（若有）
        op.execute(
            sa.text(
                """
                UPDATE user_assets
                SET team_id = (
                    SELECT teams.id FROM teams
                    WHERE teams.owner_id = user_assets.user_id
                    LIMIT 1
                )
                WHERE is_team = 1
                  AND team_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM teams WHERE teams.owner_id = user_assets.user_id
                  )
                """
            )
        )
    if "is_team" in cols:
        with op.batch_alter_table("user_assets") as batch:
            batch.drop_column("is_team")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_assets" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_assets")}
    if "is_team" not in cols:
        with op.batch_alter_table("user_assets") as batch:
            batch.add_column(
                sa.Column("is_team", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        op.execute(
            sa.text("UPDATE user_assets SET is_team = 1 WHERE team_id IS NOT NULL")
        )
