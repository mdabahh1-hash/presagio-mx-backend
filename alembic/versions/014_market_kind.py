"""Add markets.kind ('partido' | 'accesorio' | NULL): tercer nivel del rail de Deportes.

Note: Railway's startCommand skips alembic; production gets this column via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 014_market_kind
Revises: 013_market_image_url
"""

from alembic import op
import sqlalchemy as sa

revision = "014_market_kind"
down_revision = "013_market_image_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS kind VARCHAR(20)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_markets_kind ON markets (kind)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_markets_kind")
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS kind")
