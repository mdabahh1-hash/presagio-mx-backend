"""Add market_proposals table (public market suggestions)

Revision ID: 009_market_proposals
Revises: 008_follows
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "009_market_proposals"
down_revision = "008_follows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("proposer_contact", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("market_proposals")
