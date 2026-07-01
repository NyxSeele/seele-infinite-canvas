"""user profile fields (avatar, display_name, bio)

Revision ID: 012_user_profile
Revises: 011
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "avatar_url" not in cols:
        op.add_column("users", sa.Column("avatar_url", sa.String(length=512), nullable=True))
    if "display_name" not in cols:
        op.add_column("users", sa.Column("display_name", sa.String(length=64), nullable=True))
    if "bio" not in cols:
        op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "bio" in cols:
        op.drop_column("users", "bio")
    if "display_name" in cols:
        op.drop_column("users", "display_name")
    if "avatar_url" in cols:
        op.drop_column("users", "avatar_url")
