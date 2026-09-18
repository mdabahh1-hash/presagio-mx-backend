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
from app.core import lmsr
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
                "resolved_outcome_key": resolved_outcome_key, "compras": [],
            })
            m["compras"].append((side.value if side else None, outcome_key, shares))

        for (user_id, _market_id), m in per_um.items():
            if not m["resolved_at"]:
                continue
            ganador = (
                "YES" if m["status"] == MarketStatus.RESOLVED_YES
                else "NO" if m["status"] == MarketStatus.RESOLVED_NO
                else m["resolved_outcome_key"] if m["status"] == MarketStatus.RESOLVED
                else None
            )
            multi = m["status"] == MarketStatus.RESOLVED
            payout = sum(
                sh for side, key, sh in m["compras"]
                if ganador and lmsr.posicion_gana(side, key, ganador, multi)
            )
            if payout:
                db.add(PointsLedger(
                    user_id=user_id, delta=payout, reason="payout", created_at=m["resolved_at"],
                ))

        await db.commit()
