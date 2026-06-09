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
    since = today - timedelta(days=29)

    result = await db.execute(
        select(
            func.date(Trade.created_at).label("day"),
            func.sum(Trade.cost).label("spent"),
        )
        .where(Trade.user_id == current_user.id, Trade.created_at >= since.isoformat())
        .group_by(func.date(Trade.created_at))
    )
    spending_by_day = {str(row.day): row.spent for row in result.all()}

    # Walk backwards from today to reconstruct balance
    points = []
    balance = current_user.points
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        day_str = str(day)
        points.append({"date": day_str, "price": round(balance, 2)})
        balance += spending_by_day.get(day_str, 0)

    return points


@router.get("/{username}", response_model=UserPublic)
async def get_user(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user
