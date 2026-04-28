from datetime import datetime
from pydantic import BaseModel, field_validator
from app.schemas.user import UserPublic


class CommentCreate(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El comentario no puede estar vacío")
        if len(v) > 1000:
            raise ValueError("Máximo 1,000 caracteres")
        return v


class CommentOut(BaseModel):
    id: int
    market_id: str
    text: str
    likes: int
    created_at: datetime
    user: UserPublic

    model_config = {"from_attributes": True}
