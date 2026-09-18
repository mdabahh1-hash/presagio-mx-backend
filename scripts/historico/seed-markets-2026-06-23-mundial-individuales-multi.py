"""
Seed script: Bota de Oro y Balón de Oro del Mundial 2026 (mercados multi-opción).
Run from the backend directory:
  DATABASE_URL="postgresql+asyncpg://..." python seed-markets-2026-06-23-mundial-individuales-multi.py
"""
import asyncio
import math
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.outcome import Outcome
from app.models.price_history import PriceHistory
from app.core.lmsr import prices_multi


def init_qs_for_targets(targets: dict[str, float], b: float) -> dict[str, float]:
    """
    q_i = b * log(p_i / p_ref)   donde p_ref = 1/N (uniforme).
    Igual al helper de seed-markets-2026-06-23-multi.py.
    """
    n = len(targets)
    p_ref = 1.0 / n
    return {key: b * math.log((pct / 100.0) / p_ref) for key, pct in targets.items()}


MARKETS = [
    {
        "id": "mundial-2026-bota-de-oro",
        "question": "¿Quién ganará la Bota de Oro del Mundial 2026?",
        "description": (
            "La Bota de Oro premia al máximo goleador del Mundial 2026. Messi "
            "rompió el récord histórico de goles en Mundiales con 5 tantos en "
            "sus primeros dos partidos. Mbappé y Kane lo persiguen de cerca. El "
            "desempate es por asistencias y luego por menos minutos jugados."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "Gana la opción del jugador que termine como máximo goleador del "
            "torneo según las estadísticas oficiales de FIFA al cierre de la final."
        ),
        "ends_at": datetime(2026, 7, 19, 23, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "trending": True,
        "outcomes": [
            {"key": "messi",     "label": "🇦🇷 Lionel Messi",    "pct": 30.0},
            {"key": "mbappe",    "label": "🇫🇷 Kylian Mbappé",   "pct": 19.0},
            {"key": "kane",      "label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Harry Kane",      "pct": 14.0},
            {"key": "oyarzabal", "label": "🇪🇸 Mikel Oyarzabal", "pct":  6.0},
            {"key": "haaland",   "label": "🇳🇴 Erling Haaland",  "pct":  6.0},
            {"key": "yamal",     "label": "🇪🇸 Lamine Yamal",    "pct":  3.0},
            {"key": "vinicius",  "label": "🇧🇷 Vinícius Júnior", "pct":  3.0},
            {"key": "otro",      "label": "🌍 Otro",              "pct": 19.0},
        ],
    },
    {
        "id": "mundial-2026-balon-de-oro",
        "question": "¿Quién ganará el Balón de Oro al mejor jugador del Mundial 2026?",
        "description": (
            "El Balón de Oro adidas premia al mejor jugador del torneo. Suele "
            "caer en la figura del equipo que llega a la final, no "
            "necesariamente el goleador. Mbappé es favorito de mercado, con "
            "Messi, Yamal y Kane persiguiendo. Es el premio más impredecible."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "Gana la opción del jugador que reciba el Balón de Oro adidas del "
            "Mundial 2026 según el anuncio oficial de FIFA al término del torneo."
        ),
        "ends_at": datetime(2026, 7, 19, 23, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "trending": True,
        "outcomes": [
            {"key": "mbappe",     "label": "🇫🇷 Kylian Mbappé",   "pct": 16.0},
            {"key": "messi",      "label": "🇦🇷 Lionel Messi",    "pct": 13.0},
            {"key": "yamal",      "label": "🇪🇸 Lamine Yamal",    "pct": 11.0},
            {"key": "kane",       "label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Harry Kane",      "pct": 10.0},
            {"key": "olise",      "label": "🇫🇷 Michael Olise",   "pct":  8.0},
            {"key": "vinicius",   "label": "🇧🇷 Vinícius Júnior", "pct":  6.0},
            {"key": "bellingham", "label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Jude Bellingham",  "pct":  4.0},
            {"key": "pedri",      "label": "🇪🇸 Pedri",            "pct":  4.0},
            {"key": "otro",       "label": "🌍 Otro",              "pct": 28.0},
        ],
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for data in MARKETS:
            market_id = data["id"]

            # Validar que los porcentajes sumen 100
            total_pct = sum(o["pct"] for o in data["outcomes"])
            if abs(total_pct - 100.0) > 0.01:
                print(f"  WARNING  {market_id}: los pct suman {total_pct:.2f}%, no 100%")

            # Idempotente: saltar si ya existe
            exists = await db.execute(select(Market).where(Market.id == market_id))
            if exists.scalar_one_or_none() is not None:
                print(f"  SKIP     {market_id} (ya existe)")
                continue

            # a) Insertar fila padre en markets
            market = Market(
                id=market_id,
                question=data["question"],
                description=data["description"],
                category=data["category"],
                resolution_criteria=data["resolution_criteria"],
                ends_at=data["ends_at"],
                b=data["b"],
                q_yes=0.0,
                q_no=0.0,
                yes_price=0.0,
                volume=0.0,
                num_trades=0,
                status=MarketStatus.OPEN,
                trending=data["trending"],
                market_type="multi",
            )
            db.add(market)

            # b) Flush para fijar el id antes de los outcomes
            await db.flush()

            # c) Calcular q y precio inicial para cada outcome
            targets = {o["key"]: o["pct"] for o in data["outcomes"]}
            q_dict = init_qs_for_targets(targets, data["b"])
            initial_prices = prices_multi(q_dict, data["b"])

            for o in data["outcomes"]:
                key = o["key"]
                db.add(Outcome(
                    market_id=market_id,
                    outcome_key=key,
                    label=o["label"],
                    q=q_dict[key],
                    price=initial_prices[key],
                ))
                print(f"    outcome: {o['label']:25s}  target={o['pct']:5.1f}%  actual={initial_prices[key]:.2f}%")

            # d) Una fila de PriceHistory por mercado (placeholder)
            db.add(PriceHistory(market_id=market_id, yes_price=0.0, volume_snapshot=0.0))

            print(f"  INSERT   {market_id}  (multi, b={data['b']}, {len(data['outcomes'])} outcomes)")

        await db.commit()
        print("\nDone.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
