"""Add markets.resolution_source_url (link to the official source that decides the outcome).

Note: Railway's startCommand skips alembic; production gets this column via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 012_resolution_source_url
Revises: 011_subcategory
"""

from alembic import op
import sqlalchemy as sa

revision = "012_resolution_source_url"
down_revision = "011_subcategory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS resolution_source_url VARCHAR(500)")


def downgrade() -> None:
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS resolution_source_url")
