"""add streak, daily bonus, and email notification columns

Revision ID: 002_streak_notifications
Revises: 001_email_password_auth
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = "002_streak_notifications"
down_revision = "001_email_password_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_bonus_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("users", "email_notifications")
    op.drop_column("users", "last_bonus_at")
    op.drop_column("users", "streak")
