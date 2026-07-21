"""r2_files local storage columns

Revision ID: 034
Revises: 033
"""

from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "r2_files" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("r2_files")}
    if "storage_backend" not in cols:
        op.add_column(
            "r2_files",
            sa.Column("storage_backend", sa.String(length=16), nullable=False, server_default="r2"),
        )
    if "local_rel_path" not in cols:
        op.add_column(
            "r2_files",
            sa.Column("local_rel_path", sa.String(length=1024), nullable=True),
        )
    op.create_index("ix_r2_files_storage_backend", "r2_files", ["storage_backend"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "r2_files" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("r2_files")}
    if "ix_r2_files_storage_backend" in {i["name"] for i in insp.get_indexes("r2_files")}:
        op.drop_index("ix_r2_files_storage_backend", table_name="r2_files")
    if "local_rel_path" in cols:
        op.drop_column("r2_files", "local_rel_path")
    if "storage_backend" in cols:
        op.drop_column("r2_files", "storage_backend")
