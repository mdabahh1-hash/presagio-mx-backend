"""Add markets.kickoff_at (instante del evento de un mercado deportivo).

Note: Railway's startCommand skips alembic; production gets this column (and the
backfill from ends_at for partidos) via app.database.migrate_columns() at boot.
This migration keeps dev DBs in sync.

Revision ID: 018_market_kickoff_at
Revises: 017_market_sujeto
"""

from alembic import op

revision = "018_market_kickoff_at"
down_revision = "017_market_sujeto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS kickoff_at TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS ix_markets_kickoff_at ON markets (kickoff_at)")
    op.execute(
        "UPDATE markets SET kickoff_at = ends_at WHERE kickoff_at IS NULL AND (kind = 'partido' "
        "OR (kind = 'accesorio' AND sujeto->>'alcance' = 'partido'))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_markets_kickoff_at")
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS kickoff_at")
