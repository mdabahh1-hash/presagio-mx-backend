from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Outcome(Base):
    __tablename__ = "market_outcomes"
    __table_args__ = (UniqueConstraint("market_id", "outcome_key", name="uq_outcome_market_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    market_id: Mapped[str] = mapped_column(String(100), ForeignKey("markets.id"), nullable=False, index=True)
    outcome_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    q: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    market: Mapped["Market"] = relationship("Market", back_populates="outcomes")
