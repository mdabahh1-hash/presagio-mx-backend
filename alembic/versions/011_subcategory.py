"""Add markets.subcategory (free-text subcategory within a category).

Note: Railway's startCommand skips alembic; production gets this column via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 011_subcategory
Revises: 010_passkeys
"""

from alembic import op
import sqlalchemy as sa

revision = "011_subcategory"
down_revision = "010_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS subcategory VARCHAR(50)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_markets_subcategory ON markets (subcategory)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_markets_subcategory")
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS subcategory")
