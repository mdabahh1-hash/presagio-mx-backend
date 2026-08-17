"""Add follows table (user follows user)

Revision ID: 008_follows
Revises: 007_market_close_flags
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "008_follows"
down_revision = "007_market_close_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("follower_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("followed_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("follower_id", "followed_id", name="uq_follow_pair"),
    )
    op.create_index("ix_follows_follower_id", "follows", ["follower_id"])
    op.create_index("ix_follows_followed_id", "follows", ["followed_id"])


def downgrade() -> None:
    op.drop_table("follows")
