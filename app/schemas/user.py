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


class UserUpdate(BaseModel):
    display_name: str | None = None
    username: str | None = None
