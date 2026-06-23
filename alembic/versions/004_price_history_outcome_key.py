"""Add outcome_key to price_history for per-outcome tracking

Revision ID: 004_price_history_outcome_key
Revises: 003_multi_outcome
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "004_price_history_outcome_key"
down_revision = "003_multi_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_history",
        sa.Column("outcome_key", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_price_history_outcome_key",
        "price_history",
        ["market_id", "outcome_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_history_outcome_key", table_name="price_history")
    op.drop_column("price_history", "outcome_key")
