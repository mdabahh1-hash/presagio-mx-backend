import enum
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Enum, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TradeSide(str, enum.Enum):
    YES = "YES"
    NO = "NO"


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(100), ForeignKey("markets.id"), nullable=False, index=True)

    side: Mapped[TradeSide] = mapped_column(Enum(TradeSide), nullable=False)
    shares: Mapped[float] = mapped_column(Float, nullable=False)   # number of shares bought
    cost: Mapped[float] = mapped_column(Float, nullable=False)     # points spent (LMSR cost)

    # Prices before and after for slippage info
    price_before: Mapped[float] = mapped_column(Float, nullable=False)
    price_after: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user: Mapped["User"] = relationship("User", back_populates="trades")
    market: Mapped["Market"] = relationship("Market", back_populates="trades")
