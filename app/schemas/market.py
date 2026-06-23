from datetime import datetime
from pydantic import BaseModel
from app.models.market import MarketStatus, MarketCategory


class PricePoint(BaseModel):
    recorded_at: datetime
    yes_price: float
    volume_snapshot: float

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
    resolution_criteria: str
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


class MarketCreate(BaseModel):
    id: str
    question: str
    description: str
    category: MarketCategory
    resolution_criteria: str
    ends_at: datetime
    b: float = 100.0
    initial_yes_price: float = 50.0  # percentage 0-100


class MarketResolve(BaseModel):
    resolution: str | None = None   # "YES" or "NO" for binary markets
    outcome_key: str | None = None  # outcome key for multi-outcome markets
