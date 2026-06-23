"""
Seed script: multi-outcome "¿Quién ganará el Mundial 2026?" market
Run from the backend directory:
  DATABASE_URL="postgresql+asyncpg://..." python seed-markets-2026-06-23-multi.py
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.outcome import Outcome
from app.models.price_history import PriceHistory
from app.core.lmsr import prices_multi

MARKET = {
    "id": "mundial-2026-campeon",
    "question": "¿Quién ganará el Mundial 2026?",
    "description": (
        "El Mundial 2026 se disputa en México, EE.UU. y Canadá. "
        "Elige al campeón entre los principales candidatos. "
        "Los precios reflejan probabilidades actuales según mercados internacionales."
    ),
    "category": MarketCategory.MUNDIAL_2026,
    "resolution_criteria": (
        "Resuelve con el país que gane la final del 19 de julio de 2026. "
        "Se resolverá el mismo día o el siguiente hábil tras la final."
    ),
    "ends_at": "2026-07-19T22:00:00+00:00",
    "b": 300.0,
    "trending": True,
    "market_type": "multi",
    # Outcomes: label + approximate opening price (%)
    # Sum should be ~100%. LMSR initial q: set q_i such that price_i ≈ target.
    # For equal-weight start: all q_i = 0 → each = 100/N = ~12.5%
    # To match Polymarket odds, offset the qs proportionally.
    # We set q_i = b * ln(target_i) - constant, i.e. use log-odds.
    # Easiest: just use all q=0 (uniform 12.5%) and let trading find true prices.
    # But per brief, France should be higher. Set opening prices manually via q.
    # price_i = exp(q_i/b) / Σ exp(q_j/b)
    # Setting q proportional to log(target_i/reference) with reference=avg is clean.
    # We'll compute from target percentages summing to 100.
    "outcomes": [
        {"key": "france",    "label": "🇫🇷 Francia",    "target_pct": 19.0},
        {"key": "england",   "label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Inglaterra",  "target_pct": 14.0},
        {"key": "spain",     "label": "🇪🇸 España",     "target_pct": 13.0},
        {"key": "argentina", "label": "🇦🇷 Argentina",  "target_pct": 13.0},
        {"key": "germany",   "label": "🇩🇪 Alemania",   "target_pct": 10.0},
        {"key": "portugal",  "label": "🇵🇹 Portugal",   "target_pct":  8.0},
        {"key": "brazil",    "label": "🇧🇷 Brasil",     "target_pct":  7.0},
        {"key": "mexico",    "label": "🇲🇽 México",     "target_pct":  6.0},
        {"key": "otros",     "label": "🌍 Otro país",   "target_pct": 10.0},
    ],
}


import math

def init_qs_for_targets(targets: dict[str, float], b: float) -> dict[str, float]:
    """
    Return q_dict such that prices_multi(q_dict, b) ≈ targets (percentages summing to 100).
    Formula: q_i = b * log(p_i) + constant  — constant cancels in the softmax.
    We set q_i = b * log(p_i / p_ref) where p_ref = 1/N (uniform).
    """
    n = len(targets)
    p_ref = 1.0 / n  # uniform probability
    q = {}
    for key, pct in targets.items():
        p = pct / 100.0
        q[key] = b * math.log(p / p_ref)
    return q


async def main() -> None:
    async with AsyncSessionLocal() as db:
        data = MARKET

        result = await db.execute(select(Market).where(Market.id == data["id"]))
        if result.scalar_one_or_none() is not None:
            print(f"  SKIP  {data['id']} (already exists)")
            await engine.dispose()
            return

        b = data["b"]
        ends_at = datetime.fromisoformat(data["ends_at"])

        market = Market(
            id=data["id"],
            question=data["question"],
            description=data["description"],
            category=data["category"],
            resolution_criteria=data["resolution_criteria"],
            ends_at=ends_at,
            b=b,
            q_yes=0.0,
            q_no=0.0,
            yes_price=0.0,
            volume=0.0,
            num_trades=0,
            status=MarketStatus.OPEN,
            trending=data.get("trending", False),
            market_type="multi",
        )
        db.add(market)
        await db.flush()

        targets = {o["key"]: o["target_pct"] for o in data["outcomes"]}
        q_dict = init_qs_for_targets(targets, b)
        initial_prices = prices_multi(q_dict, b)

        for o in data["outcomes"]:
            key = o["key"]
            outcome = Outcome(
                market_id=market.id,
                outcome_key=key,
                label=o["label"],
                q=q_dict[key],
                price=initial_prices[key],
            )
            db.add(outcome)
            print(f"    outcome: {o['label']:20s}  target={o['target_pct']:.1f}%  actual={initial_prices[key]:.2f}%")

        db.add(PriceHistory(market_id=market.id, yes_price=0.0, volume_snapshot=0.0))

        await db.commit()
        print(f"\n  INSERT {data['id']} (multi, b={b})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
