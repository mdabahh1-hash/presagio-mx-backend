from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.models.user import User
from app.models.position import Position
from app.models.market import Market
from app.models.trade import Trade, TradeSide
from app.schemas.user import UserMe, UserPublic, UserUpdate, LeaderboardEntry, ProfilePublic
from app.schemas.trade import PositionOut
from app.core.auth import get_current_user
from app.config import settings

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
    if payload.email_notifications is not None:
        current_user.email_notifications = payload.email_notifications
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/daily-bonus")
async def claim_daily_bonus(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    last = current_user.last_bonus_at.date() if current_user.last_bonus_at else None
    if last == today:
        raise HTTPException(status_code=409, detail="Ya reclamaste tu bono de hoy")

    streak = current_user.streak + 1 if last == today - timedelta(days=1) else 1
    amount = min(100 + (streak - 1) * 20, 300)

    current_user.points += amount
    current_user.streak = streak
    current_user.last_bonus_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)
    return {"awarded": amount, "streak": streak, "new_balance": current_user.points}


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


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(limit: int = 50, db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 100))

    users_res = await db.execute(select(User).where(User.markets_traded > 0))
    users = users_res.scalars().all()
    if not users:
        return []

    # Total volume traded per user (sum of LMSR costs)
    vol_res = await db.execute(
        select(Trade.user_id, func.sum(Trade.cost)).group_by(Trade.user_id)
    )
    vol_by_user = {uid: float(s or 0) for uid, s in vol_res.all()}

    # Current value of open positions per user.
    # A winning share pays 1 PT, so a share is worth (price/100) PT right now.
    pos_res = await db.execute(
        select(Position.user_id, Position.side, Position.shares, Market.yes_price)
        .join(Market, Market.id == Position.market_id)
        .where(Position.shares > 0)
    )
    posval_by_user: dict[int, float] = {}
    for uid, side, shares, yes_price in pos_res.all():
        frac = (yes_price if side == TradeSide.YES else (100 - yes_price)) / 100.0
        posval_by_user[uid] = posval_by_user.get(uid, 0.0) + shares * frac

    base = float(settings.NEW_USER_POINTS)
    entries = [
        LeaderboardEntry(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            avatar_url=u.avatar_url,
            pnl=round(u.points + posval_by_user.get(u.id, 0.0) - base, 2),
            volume=round(vol_by_user.get(u.id, 0.0), 2),
            markets_traded=u.markets_traded,
            accuracy=u.accuracy,
        )
        for u in users
    ]
    entries.sort(key=lambda e: e.pnl, reverse=True)
    return entries[:limit]


async def _pnl_and_volume(db: AsyncSession, user: User) -> tuple[float, float]:
    """P&L (net worth − starting bonus) and total traded volume for one user."""
    vol_res = await db.execute(select(func.sum(Trade.cost)).where(Trade.user_id == user.id))
    volume = float(vol_res.scalar() or 0)

    pos_res = await db.execute(
        select(Position.side, Position.shares, Market.yes_price)
        .join(Market, Market.id == Position.market_id)
        .where(Position.user_id == user.id, Position.shares > 0)
    )
    posval = 0.0
    for side, shares, yes_price in pos_res.all():
        frac = (yes_price if side == TradeSide.YES else (100 - yes_price)) / 100.0
        posval += shares * frac

    pnl = user.points + posval - float(settings.NEW_USER_POINTS)
    return round(pnl, 2), round(volume, 2)


@router.get("/{username}", response_model=ProfilePublic)
async def get_user(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    pnl, volume = await _pnl_and_volume(db, user)
    return ProfilePublic(
        id=user.id, username=user.username, display_name=user.display_name,
        avatar_url=user.avatar_url, pnl=pnl, volume=volume,
        markets_traded=user.markets_traded, accuracy=user.accuracy, created_at=user.created_at,
    )


@router.get("/{username}/positions", response_model=list[PositionOut])
async def get_user_positions(username: str, db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    result = await db.execute(
        select(Position, Market.question)
        .join(Market, Market.id == Position.market_id)
        .where(Position.user_id == user.id, Position.shares > 0)
        .order_by(desc(Position.updated_at))
    )
    out = []
    for pos, question in result.all():
        data = PositionOut.model_validate(pos)
        data.market_question = question
        out.append(data)
    return out
