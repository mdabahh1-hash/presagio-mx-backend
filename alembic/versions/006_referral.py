"""Add referral columns to users

Revision ID: 006_referral
Revises: 005_points_ledger
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "006_referral"
down_revision = "005_points_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("referred_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("users", sa.Column("referral_credited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_credited_at")
    op.drop_column("users", "referred_by_id")
    op.drop_column("users", "referral_code")
