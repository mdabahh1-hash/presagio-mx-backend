"""widen users.avatar_url from VARCHAR(500) to TEXT

Google profile-picture URLs regularly exceed 1,000 characters; the 500-char
limit made every such Google signup fail with StringDataRightTruncationError.

Revision ID: 016_avatar_url_text
Revises: 015_market_rules_context
"""
from alembic import op
import sqlalchemy as sa

revision = "016_avatar_url_text"
down_revision = "015_market_rules_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users", "avatar_url",
        type_=sa.Text(), existing_type=sa.String(500), existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users", "avatar_url",
        type_=sa.String(500), existing_type=sa.Text(), existing_nullable=True,
    )
