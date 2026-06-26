"""One-time backfill of the points ledger from historical trades + resolutions.

Runs at startup but only when the ledger is empty, so it executes once. It
reconstructs the two event types we can timestamp precisely:
  • each trade     → −cost at trade.created_at
  • each resolution → +winning shares (1 PT each) at market.resolved_at
Daily bonuses / referrals before the ledger existed are NOT backfilled (we don't
store their per-event timestamps); from now on every delta is recorded live, so
recent period windows are exact. Older windows may understate bonus income.
"""
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models.points_ledger import PointsLedger
from app.models.trade import Trade
from app.models.market import Market, MarketStatus


async def backfill_ledger() -> None:
    async with AsyncSessionLocal() as db:
        count = await db.execute(select(func.count(PointsLedger.id)))
        if (count.scalar() or 0) > 0:
            return  # already populated → nothing to do

        res = await db.execute(
            select(
                Trade.user_id, Trade.cost, Trade.shares, Trade.side, Trade.outcome_key,
                Trade.market_id, Trade.created_at,
                Market.status, Market.resolved_at, Market.resolved_outcome_key,
            ).join(Market, Market.id == Trade.market_id)
        )
        rows = res.all()
        if not rows:
            return

        # Winning shares per (user, market), to credit payouts at resolution time.
        per_um: dict[tuple[int, str], dict] = {}
        for (user_id, cost, shares, side, outcome_key, market_id, created_at,
             status, resolved_at, resolved_outcome_key) in rows:
            db.add(PointsLedger(user_id=user_id, delta=-cost, reason="trade", created_at=created_at))

            key = (user_id, market_id)
            m = per_um.setdefault(key, {
                "status": status, "resolved_at": resolved_at,
                "resolved_outcome_key": resolved_outcome_key, "shares_by_key": {},
            })
            effective_key = outcome_key or (side.value if side else "")
            m["shares_by_key"][effective_key] = m["shares_by_key"].get(effective_key, 0.0) + shares

        for (user_id, _market_id), m in per_um.items():
            if not m["resolved_at"]:
                continue
            sbk = m["shares_by_key"]
            payout = 0.0
            if m["status"] == MarketStatus.RESOLVED_YES:
                payout = sbk.get("YES", 0.0)
            elif m["status"] == MarketStatus.RESOLVED_NO:
                payout = sbk.get("NO", 0.0)
            elif m["status"] == MarketStatus.RESOLVED and m["resolved_outcome_key"]:
                payout = sbk.get(m["resolved_outcome_key"], 0.0)
            if payout:
                db.add(PointsLedger(
                    user_id=user_id, delta=payout, reason="payout", created_at=m["resolved_at"],
                ))

        await db.commit()
