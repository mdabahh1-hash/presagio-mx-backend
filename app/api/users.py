from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.models.user import User
from app.models.position import Position
from app.models.market import Market
from app.models.trade import Trade
from app.schemas.user import UserMe, UserPublic, UserUpdate
from app.schemas.trade import PositionOut
from app.core.auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserMe)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.display_name:
        current_user.display_name = payload.display_name.strip()
    if payload.username:
        username = payload.username.strip().lower()
        exists = await db.execute(
            select(User).where(User.username == username, User.id != current_user.id)
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username ya en uso")
        current_user.username = username
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/me/positions", response_model=list[PositionOut])
async def get_my_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Position, Market.question)
        .join(Market, Market.id == Position.market_id)
        .where(Position.user_id == current_user.id, Position.shares > 0)
        .order_by(desc(Position.updated_at))
    )
    rows = result.all()
    out = []
    for pos, question in rows:
        data = PositionOut.model_validate(pos)
        data.market_question = question
        out.append(data)
    return out


@router.get("/me/points-history")
async def get_points_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    since = datetime.now(timezone.utc) - timedelta(days=29)

    result = await db.execute(
        select(Trade.created_at, Trade.cost)
        .where(Trade.user_id == current_user.id, Trade.created_at >= since)
        .order_by(Trade.created_at)
    )
    trades = result.all()

    spending_by_day: dict[str, float] = {}
    for created_at, cost in trades:
        day_str = created_at.date().isoformat()
        spending_by_day[day_str] = spending_by_day.get(day_str, 0) + cost

    history = []
    balance = current_user.points
    for i in range(30):
        day = today - timedelta(days=i)
        day_str = day.isoformat()
        history.append({"date": day_str, "price": round(balance, 2)})
        balance += spending_by_day.get(day_str, 0)

    history.reverse()
    return history


@router.get("/leaderboard", response_model=list[UserPublic])
async def get_leaderboard(limit: int = 50, db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 100))
    result = await db.execute(
        select(User)
        .where(User.markets_traded > 0)
        .order_by(desc(User.points), desc(User.correct_predictions))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{username}", response_model=UserPublic)
async def get_user(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user
