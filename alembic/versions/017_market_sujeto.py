"""Add markets.sujeto (identidad del jugador de un accesorio, ids por fuente).

Note: Railway's startCommand skips alembic; production gets this column via
app.database.migrate_columns() at boot. This migration keeps dev DBs in sync.

Revision ID: 017_market_sujeto
Revises: 016_avatar_url_text
"""

from alembic import op

revision = "017_market_sujeto"
down_revision = "016_avatar_url_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS sujeto JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE markets DROP COLUMN IF EXISTS sujeto")
