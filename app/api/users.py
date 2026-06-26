from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.user import User
from app.models.position import Position
from app.models.market import Market, MarketStatus
from app.models.trade import Trade
from app.schemas.user import UserMe, UserPublic, UserUpdate, LeaderboardEntry, ProfilePublic
from app.schemas.trade import PositionOut
from app.core.auth import get_current_user
from app.config import settings
from app.services import ledger, referral
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])

# Daily bonus "day" is anchored to Mexico time (UTC−6; Mexico has no DST since 2022)
# so the day boundary is midnight Mexico, not 6pm Mexico (UTC midnight).
MX_TZ = timezone(timedelta(hours=-6))


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
    today = datetime.now(MX_TZ).date()
    created = current_user.created_at.astimezone(MX_TZ).date() if current_user.created_at else today
    last = current_user.last_bonus_at.astimezone(MX_TZ).date() if current_user.last_bonus_at else None

    # No bonus on the day you register — first bonus is the next day you connect.
    if created == today:
        raise HTTPException(status_code=409, detail="Tu primer bono estará disponible mañana")
    if last == today:
        raise HTTPException(status_code=409, detail="Ya reclamaste tu bono de hoy")

    streak = current_user.streak + 1 if last == today - timedelta(days=1) else 1
    amount = min(100 + (streak - 1) * 20, 300)

    current_user.points += amount
    ledger.record(db, current_user.id, amount, "daily_bonus")
    current_user.streak = streak
    current_user.last_bonus_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)
    return {"awarded": amount, "streak": streak, "new_balance": current_user.points}


class ReferralAttachRequest(BaseModel):
    code: str


@router.post("/me/referral")
async def attach_referral(
    payload: ReferralAttachRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attribute the current (brand-new) user to a referral code. The bonus is
    NOT paid here — it's paid on the user's first trade. Safe to call once, only
    before any trading and only if not already attributed."""
    if current_user.referred_by_id is not None or current_user.markets_traded > 0:
        return {"ok": False, "reason": "not_eligible"}
    referrer_id = await referral.resolve_referrer(db, payload.code, current_user.email)
    if referrer_id is None:
        return {"ok": False, "reason": "invalid_code"}
    current_user.referred_by_id = referrer_id
    await db.commit()
    return {"ok": True}


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
    """Daily points balance over the last 30 days.

    Reconstructed from real events so the line starts at the 1000 PT sign-up
    grant and moves only when something actually changes the balance:
      • sign-up      → +1000 PT
      • each trade   → −cost (points spent on shares)
      • a resolution → +winning shares (1 PT each) for markets the user got right
    Any leftover (e.g. daily bonuses, whose exact timing we don't store) is
    folded in so today's value matches the real current balance.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    base = float(settings.NEW_USER_POINTS)

    # All of the user's trades, with the market's resolution state.
    res = await db.execute(
        select(
            Trade.created_at, Trade.cost, Trade.shares, Trade.side, Trade.outcome_key,
            Trade.market_id, Market.status, Market.resolved_at, Market.resolved_outcome_key,
        )
        .join(Market, Market.id == Trade.market_id)
        .where(Trade.user_id == current_user.id)
    )
    rows = res.all()

    # (timestamp, delta) events. Start from the sign-up grant.
    events: list[tuple[datetime, float]] = [(current_user.created_at or now, base)]
    per_market: dict[str, dict] = {}
    for created_at, cost, shares, side, outcome_key, market_id, status, resolved_at, resolved_outcome_key in rows:
        events.append((created_at, -cost))
        effective_key = outcome_key or (side.value if side else "")
        m = per_market.setdefault(
            market_id,
            {"status": status, "resolved_at": resolved_at, "resolved_outcome_key": resolved_outcome_key, "shares_by_key": {}},
        )
        m["shares_by_key"][effective_key] = m["shares_by_key"].get(effective_key, 0.0) + shares

    # Resolution payouts: winning shares pay 1 PT each.
    from app.models.market import MarketStatus as MS
    for m in per_market.values():
        if not m["resolved_at"]:
            continue
        sbk = m["shares_by_key"]
        if m["status"] == MS.RESOLVED_YES:
            events.append((m["resolved_at"], sbk.get("YES", 0.0)))
        elif m["status"] == MS.RESOLVED_NO:
            events.append((m["resolved_at"], sbk.get("NO", 0.0)))
        elif m["status"] == MS.RESOLVED and m["resolved_outcome_key"]:
            events.append((m["resolved_at"], sbk.get(m["resolved_outcome_key"], 0.0)))

    # Fold any residual (bonuses, manual adjustments) so the chart ends on the
    # real current balance.
    residual = current_user.points - sum(d for _, d in events)
    if abs(residual) > 0.01:
        events.append((current_user.last_bonus_at or now, residual))

    events.sort(key=lambda e: e[0])

    history = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        balance = sum(d for t, d in events if t.date() <= day)
        history.append({"date": day.isoformat(), "price": round(balance, 2)})
    return history


def _period_start(period: str) -> datetime | None:
    """Window start (UTC) for a leaderboard period, anchored to Mexico time.
    Returns None for 'all' / unknown → caller uses the all-time formula.
    """
    now_mx = datetime.now(MX_TZ)
    if period == "today":
        start_mx = now_mx.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_mx = now_mx - timedelta(days=7)
    elif period == "month":
        start_mx = now_mx - timedelta(days=30)
    else:
        return None
    return start_mx.astimezone(timezone.utc)


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(limit: int = 50, period: str = "all", db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 100))

    start = _period_start(period)
    if start is not None:
        return await _period_leaderboard(db, start, limit)

    users_res = await db.execute(select(User).where(User.markets_traded > 0))
    users = users_res.scalars().all()
    if not users:
        return []

    # Amount currently invested per user = cost basis of open positions
    # (what they have at stake right now). Used for both volume and P&L so that
    # placing a bet is P&L-neutral; P&L only moves when a market resolves.
    pos_res = await db.execute(
        select(Position.user_id, Position.shares, Position.avg_cost)
        .where(Position.shares > 0)
    )
    invested_by_user: dict[int, float] = {}
    for uid, shares, avg_cost in pos_res.all():
        invested_by_user[uid] = invested_by_user.get(uid, 0.0) + shares * avg_cost

    base = float(settings.NEW_USER_POINTS)
    entries = [
        LeaderboardEntry(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            avatar_url=u.avatar_url,
            pnl=round(u.points + invested_by_user.get(u.id, 0.0) - base, 2),
            volume=round(invested_by_user.get(u.id, 0.0), 2),
            markets_traded=u.markets_traded,
            accuracy=u.accuracy,
        )
        for u in users
    ]
    entries.sort(key=lambda e: e.pnl, reverse=True)
    return entries[:limit]


async def _period_leaderboard(db: AsyncSession, start: datetime, limit: int) -> list[LeaderboardEntry]:
    """Per-period board: realized P&L = Σ ledger deltas in window; volume = Σ trade cost."""
    from sqlalchemy import func as safunc
    from app.models.points_ledger import PointsLedger

    pnl_res = await db.execute(
        select(PointsLedger.user_id, safunc.sum(PointsLedger.delta))
        .where(PointsLedger.created_at >= start)
        .group_by(PointsLedger.user_id)
    )
    pnl_by_user = {uid: float(d or 0.0) for uid, d in pnl_res.all()}

    vol_res = await db.execute(
        select(Trade.user_id, safunc.sum(Trade.cost))
        .where(Trade.created_at >= start)
        .group_by(Trade.user_id)
    )
    vol_by_user = {uid: float(c or 0.0) for uid, c in vol_res.all()}

    active_ids = set(pnl_by_user) | set(vol_by_user)
    if not active_ids:
        return []

    users_res = await db.execute(select(User).where(User.id.in_(active_ids)))
    users = users_res.scalars().all()

    entries = [
        LeaderboardEntry(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            avatar_url=u.avatar_url,
            pnl=round(pnl_by_user.get(u.id, 0.0), 2),
            volume=round(vol_by_user.get(u.id, 0.0), 2),
            markets_traded=u.markets_traded,
            accuracy=u.accuracy,
        )
        for u in users
    ]
    entries.sort(key=lambda e: e.pnl, reverse=True)
    return entries[:limit]


async def _pnl_and_volume(db: AsyncSession, user: User) -> tuple[float, float]:
    """Realized P&L and amount currently invested for one user.

    invested = cost basis of open positions (what's at stake right now).
    pnl = points + invested − starting bonus → P&L-neutral when betting, only
    moves when a market resolves.
    """
    pos_res = await db.execute(
        select(Position.shares, Position.avg_cost)
        .where(Position.user_id == user.id, Position.shares > 0)
    )
    invested = 0.0
    for shares, avg_cost in pos_res.all():
        invested += shares * avg_cost

    pnl = user.points + invested - float(settings.NEW_USER_POINTS)
    return round(pnl, 2), round(invested, 2)


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
