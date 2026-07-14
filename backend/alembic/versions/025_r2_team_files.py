"""users.r2_access + r2_files table (team file space)

Revision ID: 025
Revises: 024
"""

from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "r2_access" not in cols:
            op.add_column(
                "users",
                sa.Column(
                    "r2_access",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )

    if "r2_files" not in tables:
        op.create_table(
            "r2_files",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(length=1024), nullable=False),
            sa.Column("filename", sa.String(length=512), nullable=False),
            sa.Column("content_type", sa.String(length=255), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("uploader_name", sa.String(length=64), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
        )
        op.create_index("ix_r2_files_key", "r2_files", ["key"], unique=True)
        op.create_index("ix_r2_files_uploader_id", "r2_files", ["uploader_id"])
        op.create_index("ix_r2_files_uploaded_at", "r2_files", ["uploaded_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "r2_files" in tables:
        op.drop_index("ix_r2_files_uploaded_at", table_name="r2_files")
        op.drop_index("ix_r2_files_uploader_id", table_name="r2_files")
        op.drop_index("ix_r2_files_key", table_name="r2_files")
        op.drop_table("r2_files")

    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "r2_access" in cols:
            op.drop_column("users", "r2_access")
