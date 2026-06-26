"""Add points_ledger table (per-window realized P&L)

Revision ID: 005_points_ledger
Revises: 004_price_history_outcome_key
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "005_points_ledger"
down_revision = "004_price_history_outcome_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "points_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_points_ledger_user_id", "points_ledger", ["user_id"])
    op.create_index("ix_points_ledger_created_at", "points_ledger", ["created_at"])
    op.create_index("ix_points_ledger_user_created", "points_ledger", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_points_ledger_user_created", table_name="points_ledger")
    op.drop_index("ix_points_ledger_created_at", table_name="points_ledger")
    op.drop_index("ix_points_ledger_user_id", table_name="points_ledger")
    op.drop_table("points_ledger")
