"""registered_models LLM routing fields + system_settings

Revision ID: 019
Revises: 018
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "registered_models" in tables:
        cols = {c["name"] for c in insp.get_columns("registered_models")}
        if "is_default_text" not in cols:
            op.add_column(
                "registered_models",
                sa.Column(
                    "is_default_text",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        if "input_price_per_million" not in cols:
            op.add_column(
                "registered_models",
                sa.Column("input_price_per_million", sa.Float(), nullable=True),
            )

    if "system_settings" not in tables:
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=128), primary_key=True),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(datetime('now'))"),
            ),
        )
        op.execute(
            sa.text(
                "INSERT INTO system_settings (key, value) VALUES "
                "('llm_routing_mode', 'fixed')"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "system_settings" in tables:
        op.drop_table("system_settings")

    if "registered_models" in tables:
        cols = {c["name"] for c in insp.get_columns("registered_models")}
        if "input_price_per_million" in cols:
            op.drop_column("registered_models", "input_price_per_million")
        if "is_default_text" in cols:
            op.drop_column("registered_models", "is_default_text")
