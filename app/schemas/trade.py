from datetime import datetime
from pydantic import BaseModel, field_validator
from app.models.trade import TradeSide


class TradeRequest(BaseModel):
    side: TradeSide
    points: float  # how many points to spend

    @field_validator("points")
    @classmethod
    def points_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("points debe ser mayor a 0")
        if v > 100_000:
            raise ValueError("Máximo 100,000 PT por operación")
        return v


class TradeResponse(BaseModel):
    id: int
    market_id: str
    side: TradeSide
    shares: float
    cost: float
    price_before: float
    price_after: float
    created_at: datetime

    # Updated state
    new_yes_price: float
    new_balance: float

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    id: int
    market_id: str
    side: TradeSide
    shares: float
    avg_cost: float
    updated_at: datetime

    model_config = {"from_attributes": True}
