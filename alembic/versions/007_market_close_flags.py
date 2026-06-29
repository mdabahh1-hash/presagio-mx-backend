"""Add closing/resolution notification flags to markets

Revision ID: 007_market_close_flags
Revises: 006_referral
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "007_market_close_flags"
down_revision = "006_referral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("closing_notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("markets", sa.Column("resolution_reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("markets", "resolution_reminded_at")
    op.drop_column("markets", "closing_notified_at")
