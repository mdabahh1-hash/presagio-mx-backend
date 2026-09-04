from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.models.market import MarketStatus, MarketCategory

# Tercer nivel del rail de Deportes (deporte → liga → tipo). Ver Market.kind.
MarketKind = Literal["partido", "accesorio"]


class PricePoint(BaseModel):
    recorded_at: datetime
    yes_price: float
    volume_snapshot: float
    outcome_key: str | None = None

    model_config = {"from_attributes": True}


class OutcomeOut(BaseModel):
    outcome_key: str
    label: str
    price: float

    model_config = {"from_attributes": True}


class MarketBase(BaseModel):
    id: str
    question: str
    description: str
    category: MarketCategory
    subcategory: str | None = None
    resolution_criteria: str
    resolution_source_url: str | None = None
    image_url: str | None = None
    kind: str | None = None
    yes_price: float
    volume: float
    num_trades: int
    status: MarketStatus
    trending: bool
    ends_at: datetime
    created_at: datetime
    market_type: str = "binary"
    outcomes: list[OutcomeOut] = []

    model_config = {"from_attributes": True}


class MarketList(MarketBase):
    pass


class MarketDetail(MarketBase):
    b: float
    q_yes: float
    q_no: float
    resolved_at: datetime | None
    resolved_outcome_key: str | None = None
    # Textos largos: solo en el detalle, no en los listados (100+ filas).
    rules: str | None = None
    context: str | None = None


class MarketCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=4000)
    category: MarketCategory
    subcategory: str | None = Field(default=None, max_length=50)
    resolution_criteria: str = Field(min_length=1, max_length=4000)
    resolution_source_url: str | None = Field(default=None, max_length=500)
    rules: str | None = Field(default=None, max_length=6000)
    context: str | None = Field(default=None, max_length=6000)
    image_url: str | None = Field(default=None, max_length=500)
    kind: MarketKind | None = None
    ends_at: datetime
    b: float = Field(default=1000.0, gt=0)  # LMSR liquidity; must be positive
    initial_yes_price: float = Field(default=50.0, ge=1, le=99)  # percentage


class MarketResolve(BaseModel):
    resolution: str | None = None   # "YES" or "NO" for binary markets
    outcome_key: str | None = None  # outcome key for multi-outcome markets
