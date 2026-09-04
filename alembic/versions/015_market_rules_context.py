"""Add markets.rules (Normas) y markets.context (Contexto del mercado).

Note: Railway's startCommand skips alembic; production gets these columns via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 015_market_rules_context
Revises: 014_market_kind
"""

from alembic import op
import sqlalchemy as sa

revision = "015_market_rules_context"
down_revision = "014_market_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS rules TEXT")
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS context TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS context")
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS rules")
