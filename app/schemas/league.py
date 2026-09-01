"""
Schemas Pydantic de Ligas Privadas v1.

Decimales se serializan como string para no perder precisión en el frontend.
market_id es el slug String(100) de markets.id.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

STAKE_MIN = Decimal("100")
PAYOUT_CAP_MULT = Decimal("20")


# ---------- requests ----------

class LeagueCreate(BaseModel):
    name: str = Field(min_length=3, max_length=60)
    min_members: int = Field(default=4, ge=2, le=50)


class CycleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    subcategory: str | None = None
    starts_at: datetime
    ends_at: datetime
    initial_stack: Decimal = Field(default=Decimal("10000"), gt=0)

    @field_validator("ends_at")
    @classmethod
    def ends_after_starts(cls, v: datetime, info):
        starts = info.data.get("starts_at")
        if starts and v <= starts:
            raise ValueError("ends_at debe ser posterior a starts_at")
        return v


class PredictionCreate(BaseModel):
    market_id: str
    outcome_id: int | None = None
    binary_side: str | None = None  # "yes" | "no"
    stake: Decimal = Field(ge=STAKE_MIN)

    @field_validator("binary_side")
    @classmethod
    def side_valido(cls, v: str | None):
        if v is not None and v not in ("yes", "no"):
            raise ValueError("binary_side debe ser 'yes' o 'no'")
        return v

    @model_validator(mode="after")
    def exactly_one_target(self):
        if (self.outcome_id is None) == (self.binary_side is None):
            raise ValueError("Especifica exactamente uno: outcome_id o binary_side")
        return self


# ---------- responses ----------

class MemberOut(BaseModel):
    user_id: int
    display_name: str
    role: str

    model_config = {"from_attributes": True}


class LeagueSummary(BaseModel):
    id: int
    name: str
    status: str
    invite_code: str
    member_count: int
    min_members: int
    cycle_name: str | None = None
    my_rank: int | None = None
    pending_picks: int = 0


class InvitePreview(BaseModel):
    name: str
    creator_name: str
    member_count: int
    min_members: int
    status: str
    cycle_name: str | None = None
    cycle_ends_at: datetime | None = None


class CycleMarketOut(BaseModel):
    market_id: str
    question: str
    market_type: str  # binary | multi
    closes_at: datetime
    is_open: bool
    outcomes: list[dict]  # [{id, outcome_key, label, price}] o [{side, price}] en binarios
    predicted_count: int
    my_prediction: dict | None = None  # {outcome_id|binary_side, stake, price_at_prediction, status, payout}


class StandingOut(BaseModel):
    user_id: int
    display_name: str
    balance: str  # Decimal como string
    hits: int
    total_resolved: int
    final_rank: int | None = None
    is_me: bool = False


class CycleOut(BaseModel):
    id: int
    cycle_number: int
    name: str
    status: str
    initial_stack: str
    starts_at: datetime
    ends_at: datetime
    my_balance: str | None = None
    markets: list[CycleMarketOut] = []


class LeagueDetail(BaseModel):
    id: int
    name: str
    status: str
    invite_code: str
    creator_id: int
    min_members: int
    members: list[MemberOut]
    current_cycle: CycleOut | None = None
    standings: list[StandingOut] = []


class PredictionOut(BaseModel):
    id: int
    market_id: str
    outcome_id: int | None
    binary_side: str | None
    stake: str
    price_at_prediction: str
    potential_payout: str  # min(stake/price, stake*20)
    status: str
    new_balance: str


class RevealRow(BaseModel):
    user_id: int
    display_name: str
    selection_label: str
    stake: str
    status: str
    payout: str | None = None
