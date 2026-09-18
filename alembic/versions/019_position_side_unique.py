"""positions: unicidad por (user, market, outcome_key, side) para el "No" de una opción en multi.

Note: Railway's startCommand skips alembic; production gets this via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 019_position_side_unique
Revises: 018_market_kickoff_at
"""

from alembic import op

revision = "019_position_side_unique"
down_revision = "018_market_kickoff_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_position_user_market_outcome_side "
        "ON positions (user_id, market_id, outcome_key, side) NULLS NOT DISTINCT"
    )
    op.execute("ALTER TABLE positions DROP CONSTRAINT IF EXISTS uq_position_user_market_outcome")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE positions ADD CONSTRAINT uq_position_user_market_outcome "
        "UNIQUE (user_id, market_id, outcome_key)"
    )
    op.execute("DROP INDEX IF EXISTS uq_position_user_market_outcome_side")
