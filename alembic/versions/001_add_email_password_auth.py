"""add email password auth columns

Revision ID: 001_email_password_auth
Revises:
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = "001_email_password_auth"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("email_verification_code", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("email_verification_expires", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verification_expires")
    op.drop_column("users", "email_verification_code")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "password_hash")
