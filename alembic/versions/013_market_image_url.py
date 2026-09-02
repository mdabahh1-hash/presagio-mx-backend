"""Add markets.image_url (square thumbnail: absolute https URL or frontend-relative path).

Note: Railway's startCommand skips alembic; production gets this column via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 013_market_image_url
Revises: 012_resolution_source_url
"""

from alembic import op
import sqlalchemy as sa

revision = "013_market_image_url"
down_revision = "012_resolution_source_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)")


def downgrade() -> None:
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS image_url")
