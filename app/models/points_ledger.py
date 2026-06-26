from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PointsLedger(Base):
    """Append-only log of every change to a user's points balance.

    Each row is a signed `delta` with a `reason`. Summing deltas inside a time
    window gives realized P&L for that window — which powers the period-based
    leaderboard (Hoy/Semanal/Mensual). The all-time leaderboard still uses the
    denormalized balance + open-position formula and does not read this table.
    """
    __tablename__ = "points_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    # "trade" | "payout" | "daily_bonus" | "referral"
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_points_ledger_user_created", "user_id", "created_at"),
    )
