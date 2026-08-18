"""Add passkeys table (WebAuthn credentials)

Revision ID: 010_passkeys
Revises: 009_market_proposals
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "010_passkeys"
down_revision = "009_market_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.String(512), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"])
    op.create_index("ix_passkeys_credential_id", "passkeys", ["credential_id"], unique=True)


def downgrade() -> None:
    op.drop_table("passkeys")
