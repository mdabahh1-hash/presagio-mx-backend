from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    market_id: Mapped[str] = mapped_column(String(100), ForeignKey("markets.id"), nullable=False, index=True)
    yes_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume_snapshot: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    market: Mapped["Market"] = relationship("Market", back_populates="price_history")
