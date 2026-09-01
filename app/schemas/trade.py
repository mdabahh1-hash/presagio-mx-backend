from datetime import datetime
from pydantic import BaseModel, field_validator, model_validator
from app.models.trade import TradeSide


class TradeRequest(BaseModel):
    side: TradeSide | None = None          # binary markets
    outcome_key: str | None = None         # multi-outcome markets
    points: float
    # Avg fill price (pct 0-100) the client was quoted. If present, execution
    # rejects with 409 PRICE_MOVED when the real avg fill deviates more than
    # settings.PRICE_TOLERANCE (relative).
    quoted_avg_price: float | None = None

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


class QuoteOut(BaseModel):
    """Simulated execution against the live LMSR state — the single source of
    truth for what a buy of `amount` PT would actually get.

    All price fields are on the 0-100 percent scale (repo convention).
    LMSR notes: there is no bid/ask, so spread_pct is always 0.0 (kept for
    API-shape compatibility), and partial fills are impossible (the AMM has
    unbounded liquidity) — big orders surface as slippage instead.
    """
    market_id: str
    market_type: str                       # "binary" | "multi"
    side: TradeSide | None = None
    outcome_key: str | None = None
    amount: float                          # requested PT

    mid_price: float                       # spot for the chosen side/outcome (2dp)
    mid_yes_price: float                   # binary: YES spot; multi: chosen outcome spot (2dp)
    mid_no_price: float                    # exactly 100 - mid_yes_price (derived, never rounded independently)
    avg_fill_price: float                  # cost/shares — "Precio promedio de ejecución" (2dp)
    price_after: float                     # spot after the simulated trade (2dp)

    shares: float                          # 4dp
    potential_payout: float                # PT if it resolves in your favor (= shares, 2dp)
    potential_gain: float                  # potential_payout - max_loss (Decimal-exact vs those two)
    max_loss: float                        # PT spent (2dp)
    slippage_cost: float                   # PT paid above spot for order size (2dp)

    spread_pct: float                      # always 0.0 in LMSR
    slippage_pct: float                    # (avg_fill - mid)/mid * 100 (2dp)
    liquidity_warning: bool                # unrounded slippage fraction > 0.02
    quote_expires_at: datetime


class PositionOut(BaseModel):
    id: int
    market_id: str
    market_question: str = ""
    side: TradeSide | None = None
    outcome_key: str | None = None
    shares: float
    avg_cost: float
    updated_at: datetime
    # Live LMSR mark: price in 0-1 (same scale as avg_cost), value in PT.
    # None when the market is no longer tradeable.
    current_price: float | None = None
    current_value: float | None = None

    model_config = {"from_attributes": True}
