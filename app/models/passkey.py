from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Passkey(Base):
    """A WebAuthn credential (passkey) bound to a user account."""
    __tablename__ = "passkeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)  # base64url
    public_key: Mapped[str] = mapped_column(Text, nullable=False)  # base64url COSE key bytes
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transports: Mapped[str | None] = mapped_column(String(100), nullable=True)  # comma-joined
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
