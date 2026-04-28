from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # OAuth
    google_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    github_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    # Balance
    points: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)

    # Stats (denormalized for speed)
    markets_traded: Mapped[int] = mapped_column(Integer, default=0)
    correct_predictions: Mapped[int] = mapped_column(Integer, default=0)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    trades: Mapped[list["Trade"]] = relationship("Trade", back_populates="user", lazy="select")
    positions: Mapped[list["Position"]] = relationship("Position", back_populates="user", lazy="select")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="user", lazy="select")

    @property
    def accuracy(self) -> float:
        if self.total_predictions == 0:
            return 0.0
        return round(self.correct_predictions / self.total_predictions * 100, 1)
