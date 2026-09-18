from datetime import datetime
from sqlalchemy import String, Float, DateTime, Enum, Integer, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.trade import TradeSide


class Position(Base):
    __tablename__ = "positions"
    # Una posición por (usuario, mercado, opción, lado). En multi, side NULL es el
    # Sí de la opción y side NO el No de la opción; NULLS NOT DISTINCT hace que
    # dos Sí de la misma opción choquen (PG ≥ 15). Prod lo crea en migrate_columns.
    __table_args__ = (
        Index(
            "uq_position_user_market_outcome_side",
            "user_id", "market_id", "outcome_key", "side",
            unique=True, postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(100), ForeignKey("markets.id"), nullable=False, index=True)

    side: Mapped[TradeSide | None] = mapped_column(Enum(TradeSide), nullable=True)
    outcome_key: Mapped[str] = mapped_column(String(100), nullable=False, server_default="YES")
    shares: Mapped[float] = mapped_column(Float, default=0.0)   # total shares held
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0) # average cost per share

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="positions")
    market: Mapped["Market"] = relationship("Market", back_populates="positions")
