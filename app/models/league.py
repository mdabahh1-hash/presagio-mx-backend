"""
Modelos de Ligas Privadas v1.

Todo lo monetario es NUMERIC, nunca float. Son tablas nuevas: se crean con
el create_all del startup (registradas vía app/models/__init__.py).

REGLA DURA: las ligas no tocan el trade path ni el AMM; solo leen precio.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    invite_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    # pending -> active -> archived
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    min_members: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LeagueMember(Base):
    __tablename__ = "league_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="member")  # creator | member
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("league_id", "user_id", name="uq_league_member"),)


class LeagueCycle(Base):
    __tablename__ = "league_cycles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), nullable=False, index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)  # "Jornada 8 Liga MX"
    subcategory: Mapped[str | None] = mapped_column(Text)  # fuente del seed automático
    initial_stack: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("10000")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # open -> scoring -> resolved
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("league_id", "cycle_number", name="uq_league_cycle"),)


class LeagueCycleMarket(Base):
    __tablename__ = "league_cycle_markets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("league_cycles.id"), nullable=False, index=True
    )
    # markets.id es un slug String(100), no un entero
    market_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("markets.id"), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("cycle_id", "market_id", name="uq_cycle_market"),)


class LeagueCycleStanding(Base):
    __tablename__ = "league_cycle_standings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("league_cycles.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    final_rank: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("cycle_id", "user_id", name="uq_cycle_user"),)


class LeaguePrediction(Base):
    __tablename__ = "league_predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("league_cycles.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("markets.id"), nullable=False, index=True
    )
    outcome_id: Mapped[int | None] = mapped_column(ForeignKey("market_outcomes.id"))  # multi
    binary_side: Mapped[str | None] = mapped_column(Text)  # "yes" | "no" en binarios
    stake: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    price_at_prediction: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    payout: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    # open | won | lost | void
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("cycle_id", "user_id", "market_id", name="uq_cycle_user_market"),
        CheckConstraint("stake > 0", name="ck_lp_stake_positive"),
        CheckConstraint(
            "(outcome_id IS NOT NULL AND binary_side IS NULL) "
            "OR (outcome_id IS NULL AND binary_side IS NOT NULL)",
            name="ck_lp_one_target",
        ),
    )
