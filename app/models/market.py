import enum
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Enum, Text, Integer, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MarketStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    RESOLVED_YES = "resolved_yes"
    RESOLVED_NO = "resolved_no"
    CANCELLED = "cancelled"


class MarketCategory(str, enum.Enum):
    POLITICA_MX = "Política MX"
    ECONOMIA = "Economía"
    DEPORTES = "Deportes"
    GLOBAL = "Global"
    TECH = "Tech"
    ENTRETENIMIENTO = "Entretenimiento"


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[MarketCategory] = mapped_column(Enum(MarketCategory), nullable=False, index=True)
    resolution_criteria: Mapped[str] = mapped_column(Text, nullable=False)

    # LMSR parameters
    # b controls liquidity: higher b = less price movement per trade
    b: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    # Outstanding shares for each outcome (LMSR state)
    q_yes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    q_no: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Cached current price (yes probability, 0-100)
    yes_price: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    # Volume and liquidity tracking
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    num_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[MarketStatus] = mapped_column(
        Enum(MarketStatus), default=MarketStatus.OPEN, nullable=False, index=True
    )
    trending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trades: Mapped[list["Trade"]] = relationship("Trade", back_populates="market", lazy="select")
    positions: Mapped[list["Position"]] = relationship("Position", back_populates="market", lazy="select")
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="market", lazy="select", order_by="Comment.created_at.desc()"
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="market", lazy="select", order_by="PriceHistory.recorded_at"
    )
