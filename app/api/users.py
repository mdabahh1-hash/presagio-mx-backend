from datetime import date, datetime, time, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func as safunc
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.user import User
from app.models.position import Position
from app.models.market import Market, MarketStatus
from app.models.trade import Trade, TradeSide
from app.models.follow import Follow
from app.models.outcome import Outcome
from app.models.points_ledger import PointsLedger
from app.schemas.user import (
    UserMe, UserPublic, UserUpdate, LeaderboardEntry, ProfilePublic,
    FollowedUserOut, FeedTradeOut, HistoryEventOut,
)
from app.schemas.trade import PositionOut
from app.core import lmsr
from app.core.auth import get_current_user, get_current_user_optional
from app.config import settings
from app.services import ledger, referral
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])

# Daily bonus "day" is anchored to Mexico time (UTC−6; Mexico has no DST since 2022)
# so the day boundary is midnight Mexico, not 6pm Mexico (UTC midnight).
MX_TZ = timezone(timedelta(hours=-6))


@router.get("/me", response_model=UserMe)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.passkey import Passkey
    me = UserMe.model_validate(current_user)
    pk = await db.execute(select(Passkey.id).where(Passkey.user_id == current_user.id).limit(1))
    me.has_passkey = pk.scalar_one_or_none() is not None
    return me


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
            raise HTTPException(status_code=409, detail={"code": "USERNAME_TAKEN", "message": "Username ya en uso"})
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
    # Lock the user row so two concurrent claims can't both pass the "already
    # claimed today" check and double-award.
    await db.execute(select(User).where(User.id == current_user.id).with_for_update())

    today = datetime.now(MX_TZ).date()
    created = current_user.created_at.astimezone(MX_TZ).date() if current_user.created_at else today
    last = current_user.last_bonus_at.astimezone(MX_TZ).date() if current_user.last_bonus_at else None

    # No bonus on the day you register — first bonus is the next day you connect.
    if created == today:
        raise HTTPException(status_code=409, detail={"code": "BONUS_FIRST_DAY", "message": "Tu primer bono estará disponible mañana"})
    if last == today:
        raise HTTPException(status_code=409, detail={"code": "BONUS_ALREADY_CLAIMED", "message": "Ya reclamaste tu bono de hoy"})

    streak = current_user.streak + 1 if last == today - timedelta(days=1) else 1
    amount = min(1000 + (streak - 1) * 200, 3000)

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


async def _enrich_positions(
    db: AsyncSession, rows: list[tuple[Position, Market]]
) -> list[PositionOut]:
    """PositionOut list with live LMSR marks (current_price 0-1, current_value PT).

    Prices come from q_* via app.core.lmsr — never the cached Market.yes_price
    column (0-100 scale). Markets past trading keep None marks.
    """
    tradeable = {MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION}

    multi_ids = {
        m.id for _, m in rows if m.market_type == "multi" and m.status in tradeable
    }
    q_by_market: dict[str, dict[str, float]] = {}
    if multi_ids:
        res = await db.execute(select(Outcome).where(Outcome.market_id.in_(multi_ids)))
        for o in res.scalars().all():
            q_by_market.setdefault(o.market_id, {})[o.outcome_key] = o.q

    out = []
    for pos, market in rows:
        data = PositionOut.model_validate(pos)
        data.market_question = market.question

        price: float | None = None
        if market.status in tradeable:
            if market.market_type == "multi":
                q_dict = q_by_market.get(market.id)
                if q_dict and pos.outcome_key in q_dict:
                    price = lmsr.outcome_price(q_dict, market.b, pos.outcome_key)
            elif pos.side is not None:
                p_yes = lmsr.yes_price(market.q_yes, market.q_no, market.b)
                price = p_yes if pos.side == TradeSide.YES else 1.0 - p_yes

        if price is not None:
            data.current_price = round(price, 4)
            data.current_value = round(pos.shares * price, 2)
        out.append(data)
    return out


@router.get("/me/positions", response_model=list[PositionOut])
async def get_my_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Position, Market)
        .join(Market, Market.id == Position.market_id)
        .where(Position.user_id == current_user.id, Position.shares > 0)
        .order_by(desc(Position.updated_at))
    )
    return await _enrich_positions(db, result.all())


@router.get("/me/points-history")
async def get_points_history(
    days: int = Query(30, ge=2, le=366),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily points balance over the last `days` days (Mexico-time days).

    Walks BACKWARD from the live balance subtracting points_ledger deltas per
    day: exact for any window the ledger covers, and never invents a zero
    balance. The sign-up grant has no ledger row — it's implicitly part of the
    balance — and days before the account existed are not emitted.
    """
    today_mx = datetime.now(MX_TZ).date()
    created_mx = current_user.created_at.astimezone(MX_TZ).date() if current_user.created_at else today_mx
    start_day = max(today_mx - timedelta(days=days - 1), created_mx)

    window_start_utc = datetime.combine(start_day, time.min, MX_TZ).astimezone(timezone.utc)
    res = await db.execute(
        select(PointsLedger.created_at, PointsLedger.delta)
        .where(
            PointsLedger.user_id == current_user.id,
            PointsLedger.created_at >= window_start_utc,
        )
    )
    delta_by_day: dict[date, float] = {}
    for created_at, delta in res.all():
        d = created_at.astimezone(MX_TZ).date()
        delta_by_day[d] = delta_by_day.get(d, 0.0) + delta

    # Balance at close of day D−1 = balance at close of D − deltas during D.
    history: list[dict] = []
    bal = current_user.points
    day = today_mx
    while day >= start_day:
        history.append({"date": day.isoformat(), "price": round(bal, 2)})
        bal -= delta_by_day.get(day, 0.0)
        day -= timedelta(days=1)
    history.reverse()

    # The chart needs ≥2 points; on sign-up day, pad with a flat previous day.
    if len(history) == 1:
        history.insert(0, {"date": (start_day - timedelta(days=1)).isoformat(),
                           "price": history[0]["price"]})
    return history


@router.get("/me/following", response_model=list[FollowedUserOut])
async def get_my_following(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Users the current user follows, with their P&L, points and top open
    positions. 2 queries per followed user — fine at current scale; if it ever
    matters, batch like the leaderboard's invested_by_user dict."""
    res = await db.execute(
        select(User, Follow.created_at)
        .join(Follow, Follow.followed_id == User.id)
        .where(Follow.follower_id == current_user.id)
        .order_by(desc(Follow.created_at))
    )
    out = []
    for u, followed_at in res.all():
        pnl, volume = await _pnl_and_volume(db, u)
        pos_res = await db.execute(
            select(Position, Market.question)
            .join(Market, Market.id == Position.market_id)
            .where(Position.user_id == u.id, Position.shares > 0)
            .order_by(desc(Position.updated_at))
        )
        pos_rows = pos_res.all()
        top_positions = []
        for pos, question in pos_rows[:3]:
            data = PositionOut.model_validate(pos)
            data.market_question = question
            top_positions.append(data)
        out.append(FollowedUserOut(
            id=u.id, username=u.username, display_name=u.display_name,
            avatar_url=u.avatar_url, pnl=pnl, volume=volume,
            markets_traded=u.markets_traded, accuracy=u.accuracy,
            points=round(u.points, 2), followed_at=followed_at,
            positions_count=len(pos_rows), top_positions=top_positions,
        ))
    return out


@router.get("/me/feed", response_model=list[FeedTradeOut])
async def get_my_feed(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent trades by the users the current user follows, newest first."""
    limit = max(1, min(limit, 100))
    res = await db.execute(
        select(Trade, User, Market, Outcome.label)
        .join(Follow, Follow.followed_id == Trade.user_id)
        .join(User, User.id == Trade.user_id)
        .join(Market, Market.id == Trade.market_id)
        .outerjoin(Outcome, (Outcome.market_id == Trade.market_id) & (Outcome.outcome_key == Trade.outcome_key))
        .where(Follow.follower_id == current_user.id)
        .order_by(desc(Trade.created_at))
        .limit(limit)
    )
    return [
        FeedTradeOut(
            id=t.id, created_at=t.created_at,
            side=t.side.value if t.side else None,
            outcome_key=t.outcome_key, outcome_label=outcome_label,
            shares=round(t.shares, 2), cost=round(t.cost, 2), price_after=round(t.price_after, 1),
            username=u.username, display_name=u.display_name, avatar_url=u.avatar_url,
            market_id=m.id, market_question=m.question,
            market_status=m.status.value, market_type=m.market_type,
        )
        for t, u, m, outcome_label in res.all()
    ]


async def _build_history(
    db: AsyncSession, user_id: int, limit: int, include_grants: bool,
) -> list[HistoryEventOut]:
    """Chronological account activity, newest first: buys, resolved markets
    (won/lost) and — for the owner — bonus/referral/adjustment credits.

    Resolutions are rebuilt by aggregating trades per (market, outcome):
    resolving zeroes Position.shares and losing payouts never reach the ledger,
    so neither of those sources can tell the full story on its own.
    """
    events: list[HistoryEventOut] = []

    # Buys (the platform is buy-only).
    res = await db.execute(
        select(Trade, Market, Outcome.label)
        .join(Market, Market.id == Trade.market_id)
        .outerjoin(Outcome, (Outcome.market_id == Trade.market_id) & (Outcome.outcome_key == Trade.outcome_key))
        .where(Trade.user_id == user_id)
        .order_by(desc(Trade.created_at))
        .limit(limit)
    )
    for t, m, outcome_label in res.all():
        events.append(HistoryEventOut(
            type="trade", created_at=t.created_at, amount=round(-t.cost, 2),
            market_id=m.id, market_question=m.question,
            side=t.side.value if t.side else None,
            outcome_key=t.outcome_key, outcome_label=outcome_label,
            shares=round(t.shares, 2), price_after=round(t.price_after, 1),
        ))

    # Resolutions: aggregate this user's trades per (market, effective outcome)
    # and compare against the winning key — same pattern as ledger_backfill.
    res = await db.execute(
        select(
            Trade.market_id, Trade.outcome_key, Trade.side, Trade.shares, Trade.cost,
            Market.question, Market.status, Market.resolved_at, Market.resolved_outcome_key,
            Outcome.label,
        )
        .join(Market, Market.id == Trade.market_id)
        .outerjoin(Outcome, (Outcome.market_id == Trade.market_id) & (Outcome.outcome_key == Trade.outcome_key))
        .where(
            Trade.user_id == user_id,
            Market.resolved_at.is_not(None),
            Market.status.in_((MarketStatus.RESOLVED_YES, MarketStatus.RESOLVED_NO, MarketStatus.RESOLVED)),
        )
    )
    groups: dict[tuple[str, str], dict] = {}
    for (market_id, outcome_key, side, shares, cost, question,
         status, resolved_at, resolved_key, outcome_label) in res.all():
        effective_key = outcome_key or (side.value if side else "")
        g = groups.setdefault((market_id, effective_key), {
            "shares": 0.0, "cost": 0.0, "question": question, "status": status,
            "resolved_at": resolved_at, "resolved_key": resolved_key,
            "side": None, "outcome_key": None, "outcome_label": None,
        })
        g["shares"] += shares
        g["cost"] += cost
        g["side"] = g["side"] or (side.value if side else None)
        g["outcome_key"] = g["outcome_key"] or outcome_key
        g["outcome_label"] = g["outcome_label"] or outcome_label
    for (market_id, effective_key), g in groups.items():
        winning_key = (
            "YES" if g["status"] == MarketStatus.RESOLVED_YES
            else "NO" if g["status"] == MarketStatus.RESOLVED_NO
            else g["resolved_key"]
        )
        won = bool(winning_key) and effective_key == winning_key
        events.append(HistoryEventOut(
            type="win" if won else "loss",
            created_at=g["resolved_at"],
            amount=round(g["shares"], 2) if won else round(-g["cost"], 2),
            market_id=market_id, market_question=g["question"],
            side=g["side"], outcome_key=g["outcome_key"],
            outcome_label=g["outcome_label"],
            shares=round(g["shares"], 2) if won else None,
        ))

    # Credits straight from the ledger (owner only). "trade"/"payout" rows are
    # already represented by the buy/resolution events above.
    if include_grants:
        res = await db.execute(
            select(PointsLedger.delta, PointsLedger.reason, PointsLedger.created_at)
            .where(
                PointsLedger.user_id == user_id,
                PointsLedger.reason.in_(("daily_bonus", "referral", "adjustment")),
            )
            .order_by(desc(PointsLedger.created_at))
            .limit(limit)
        )
        for delta, reason, created_at in res.all():
            events.append(HistoryEventOut(type=reason, created_at=created_at, amount=round(delta, 2)))

    events.sort(key=lambda e: e.created_at, reverse=True)
    return events[:limit]


@router.get("/me/history", response_model=list[HistoryEventOut])
async def get_my_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Own account activity: buys + resolutions + bonus/referral/adjustment credits."""
    limit = max(1, min(limit, 100))
    return await _build_history(db, current_user.id, limit, include_grants=True)


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
    # Trading P&L only — exclude daily_bonus / referral so bonus claimers don't
    # top the board over actual traders.
    pnl_res = await db.execute(
        select(PointsLedger.user_id, safunc.sum(PointsLedger.delta))
        .where(PointsLedger.created_at >= start, PointsLedger.reason.in_(("trade", "payout")))
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


async def _followers_count(db: AsyncSession, user_id: int) -> int:
    res = await db.execute(
        select(safunc.count()).select_from(Follow).where(Follow.followed_id == user_id)
    )
    return res.scalar_one()


@router.get("/{username}", response_model=ProfilePublic)
async def get_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado"})
    pnl, volume = await _pnl_and_volume(db, user)

    followers_count = await _followers_count(db, user.id)
    following_res = await db.execute(
        select(safunc.count()).select_from(Follow).where(Follow.follower_id == user.id)
    )
    following_count = following_res.scalar_one()

    is_following = None  # anónimo o perfil propio
    if viewer is not None and viewer.id != user.id:
        pair = await db.execute(
            select(Follow.id).where(Follow.follower_id == viewer.id, Follow.followed_id == user.id)
        )
        is_following = pair.scalar_one_or_none() is not None

    return ProfilePublic(
        id=user.id, username=user.username, display_name=user.display_name,
        avatar_url=user.avatar_url, pnl=pnl, volume=volume,
        markets_traded=user.markets_traded, accuracy=user.accuracy, created_at=user.created_at,
        followers_count=followers_count, following_count=following_count, is_following=is_following,
    )


@router.post("/{username}/follow")
async def follow_user(
    username: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado"})
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail={"code": "CANNOT_FOLLOW_SELF", "message": "No puedes seguirte a ti mismo"})

    exists = await db.execute(
        select(Follow.id).where(Follow.follower_id == current_user.id, Follow.followed_id == target.id)
    )
    if exists.scalar_one_or_none() is None:
        db.add(Follow(follower_id=current_user.id, followed_id=target.id))
        try:
            await db.commit()
        except IntegrityError:
            # Doble tap concurrente contra uq_follow_pair → ya siguiendo.
            await db.rollback()

    return {"following": True, "followers_count": await _followers_count(db, target.id)}


@router.delete("/{username}/follow")
async def unfollow_user(
    username: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado"})

    pair = await db.execute(
        select(Follow).where(Follow.follower_id == current_user.id, Follow.followed_id == target.id)
    )
    follow = pair.scalar_one_or_none()
    if follow is not None:
        await db.delete(follow)
        await db.commit()

    return {"following": False, "followers_count": await _followers_count(db, target.id)}


@router.get("/{username}/positions", response_model=list[PositionOut])
async def get_user_positions(username: str, db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado"})
    result = await db.execute(
        select(Position, Market)
        .join(Market, Market.id == Position.market_id)
        .where(Position.user_id == user.id, Position.shares > 0)
        .order_by(desc(Position.updated_at))
    )
    return await _enrich_positions(db, result.all())


@router.get("/{username}/history", response_model=list[HistoryEventOut])
async def get_user_history(username: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Public activity for a profile: buys and resolutions only — no credits
    (bonuses/referrals/adjustments stay private to the owner)."""
    limit = max(1, min(limit, 100))
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado"})
    return await _build_history(db, user.id, limit, include_grants=False)
