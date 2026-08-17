from datetime import datetime
from sqlalchemy import DateTime, Integer, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Follow(Base):
    """User-follows-user edge (follower_id sigue a followed_id)."""
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followed_id", name="uq_follow_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    followed_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
