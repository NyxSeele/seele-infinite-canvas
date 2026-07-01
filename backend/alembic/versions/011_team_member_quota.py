"""team member invite quota settings

Revision ID: 011_team_member_quota
Revises: 010_team_invites
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("team_members")}
    if "quota_settings" not in cols:
        op.add_column("team_members", sa.Column("quota_settings", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("team_members")}
    if "quota_settings" in cols:
        op.drop_column("team_members", "quota_settings")
