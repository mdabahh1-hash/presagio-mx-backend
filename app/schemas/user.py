from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None
    points: float
    markets_traded: int
    accuracy: float
    created_at: datetime

    model_config = {"from_attributes": True}


class UserMe(UserPublic):
    email: str
    correct_predictions: int
    total_predictions: int
    streak: int
    last_bonus_at: datetime | None
    email_notifications: bool
    referral_code: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    username: str | None = None
    email_notifications: bool | None = None


class LeaderboardEntry(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None
    pnl: float
    volume: float
    markets_traded: int
    accuracy: float


class ProfilePublic(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None
    pnl: float
    volume: float
    markets_traded: int
    accuracy: float
    created_at: datetime

    model_config = {"from_attributes": True}
