"""Add multi-outcome market support

Revision ID: 003_multi_outcome
Revises: 002_streak_notifications
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "003_multi_outcome"
down_revision = "002_streak_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New market_outcomes table
    op.create_table(
        "market_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("market_id", sa.String(100), sa.ForeignKey("markets.id"), nullable=False, index=True),
        sa.Column("outcome_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("q", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("market_id", "outcome_key", name="uq_outcome_market_key"),
    )

    # 2. Add RESOLVED to marketstatus enum (PostgreSQL requires ALTER TYPE)
    op.execute("ALTER TYPE marketstatus ADD VALUE IF NOT EXISTS 'RESOLVED'")

    # 3. Add market_type and resolved_outcome_key to markets
    op.add_column("markets", sa.Column("market_type", sa.String(20), nullable=False, server_default="binary"))
    op.add_column("markets", sa.Column("resolved_outcome_key", sa.String(100), nullable=True))

    # 4. Add outcome_key to trades (nullable — backfill from side)
    op.add_column("trades", sa.Column("outcome_key", sa.String(100), nullable=True))
    op.execute("UPDATE trades SET outcome_key = side::text WHERE outcome_key IS NULL")

    # 5. Add outcome_key to positions and migrate unique constraint
    op.add_column("positions", sa.Column("outcome_key", sa.String(100), nullable=True))
    op.execute("UPDATE positions SET outcome_key = side::text WHERE outcome_key IS NULL")
    op.alter_column("positions", "outcome_key", nullable=False)

    # Make side nullable on both tables (multi-outcome trades have no side)
    op.alter_column("trades", "side", nullable=True)
    op.alter_column("positions", "side", nullable=True)

    # Replace unique constraint on positions
    op.drop_constraint("uq_position_user_market_side", "positions", type_="unique")
    op.create_unique_constraint(
        "uq_position_user_market_outcome",
        "positions",
        ["user_id", "market_id", "outcome_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_position_user_market_outcome", "positions", type_="unique")
    op.create_unique_constraint(
        "uq_position_user_market_side",
        "positions",
        ["user_id", "market_id", "side"],
    )
    op.alter_column("positions", "side", nullable=False)
    op.alter_column("trades", "side", nullable=False)
    op.drop_column("positions", "outcome_key")
    op.drop_column("trades", "outcome_key")
    op.drop_column("markets", "resolved_outcome_key")
    op.drop_column("markets", "market_type")
    op.drop_table("market_outcomes")
    # Note: PostgreSQL does not support removing enum values; RESOLVED stays.
