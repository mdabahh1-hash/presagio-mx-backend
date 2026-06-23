from datetime import datetime
from pydantic import BaseModel, field_validator, model_validator
from app.models.trade import TradeSide


class TradeRequest(BaseModel):
    side: TradeSide | None = None          # binary markets
    outcome_key: str | None = None         # multi-outcome markets
    points: float

    @field_validator("points")
    @classmethod
    def points_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("points debe ser mayor a 0")
        if v > 100_000:
            raise ValueError("Máximo 100,000 PT por operación")
        return v

    @model_validator(mode="after")
    def exactly_one_target(self) -> "TradeRequest":
        has_side = self.side is not None
        has_outcome = self.outcome_key is not None
        if not has_side and not has_outcome:
            raise ValueError("Debes especificar 'side' (binario) o 'outcome_key' (multi-resultado)")
        if has_side and has_outcome:
            raise ValueError("Especifica solo 'side' o 'outcome_key', no ambos")
        return self


class TradeResponse(BaseModel):
    id: int
    market_id: str
    side: TradeSide | None = None
    outcome_key: str | None = None
    shares: float
    cost: float
    price_before: float
    price_after: float
    created_at: datetime

    new_yes_price: float
    new_balance: float

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    id: int
    market_id: str
    market_question: str = ""
    side: TradeSide | None = None
    outcome_key: str | None = None
    shares: float
    avg_cost: float
    updated_at: datetime

    model_config = {"from_attributes": True}
