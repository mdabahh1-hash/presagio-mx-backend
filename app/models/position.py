from datetime import datetime
from sqlalchemy import String, Float, DateTime, Enum, Integer, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.trade import TradeSide


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "market_id", "side", name="uq_position_user_market_side"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(100), ForeignKey("markets.id"), nullable=False, index=True)

    side: Mapped[TradeSide] = mapped_column(Enum(TradeSide), nullable=False)
    shares: Mapped[float] = mapped_column(Float, default=0.0)   # total shares held
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0) # average cost per share

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="positions")
    market: Mapped["Market"] = relationship("Market", back_populates="positions")
