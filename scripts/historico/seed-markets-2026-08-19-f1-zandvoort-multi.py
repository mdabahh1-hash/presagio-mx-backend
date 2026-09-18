"""
Seed script: 2 mercados MULTI-OPCIÓN del GP de Países Bajos 2026 (Zandvoort, 23 ago).
  #1 f1-paisesbajos-2026-piloto-ganador     (22 opciones — pilotos)
  #2 f1-paisesbajos-2026-escuderia-ganadora (11 opciones — escuderías)

Mirrors seed-markets-2026-06-23-multi.py (template multi-outcome).
Run from the backend directory:
  DATABASE_URL="postgresql+asyncpg://..." python seed-markets-2026-08-19-f1-zandvoort-multi.py

Resolución (manual, fuera de este script): POST /admin/markets/{id}/resolve
con el outcome_key ganador.
"""
import asyncio
import math
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

MARKETS = [
    {
        "id": "f1-paisesbajos-2026-piloto-ganador",
        "question": "¿Qué piloto ganará el GP de Países Bajos 2026?",
        "description": (
            "Carrera principal del Gran Premio de Países Bajos 2026 en Zandvoort, "
            "domingo 23 de agosto. Fin de semana con formato Sprint, pero el Sprint "
            "del sábado NO forma parte de este mercado. Última edición del GP en este circuito."
        ),
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": (
            "Piloto clasificado oficialmente en primer lugar de la carrera principal "
            "del domingo según la clasificación oficial de la FIA publicada en "
            "formula1.com, incluyendo penalizaciones posteriores aplicadas el mismo día. "
            "El Sprint no cuenta. Si la carrera se cancela o gana un piloto sustituto "
            "no listado, el mercado se cancela."
        ),
        "ends_at": "2026-08-23T10:00:00Z",
        "b": 100.0,
        "trending": True,
        "market_type": "multi",
        "outcomes": [
            {"key": "antonelli",  "label": "🇮🇹 Kimi Antonelli (Mercedes)",      "target_pct": 30.0},
            {"key": "russell",    "label": "🇬🇧 George Russell (Mercedes)",      "target_pct": 14.0},
            {"key": "hamilton",   "label": "🇬🇧 Lewis Hamilton (Ferrari)",       "target_pct": 13.0},
            {"key": "leclerc",    "label": "🇲🇨 Charles Leclerc (Ferrari)",      "target_pct": 10.0},
            {"key": "norris",     "label": "🇬🇧 Lando Norris (McLaren)",         "target_pct": 10.0},
            {"key": "verstappen", "label": "🇳🇱 Max Verstappen (Red Bull)",      "target_pct": 9.0},
            {"key": "piastri",    "label": "🇦🇺 Oscar Piastri (McLaren)",        "target_pct": 7.0},
            {"key": "hadjar",     "label": "🇫🇷 Isack Hadjar (Red Bull)",        "target_pct": 1.2},
            {"key": "sainz",      "label": "🇪🇸 Carlos Sainz (Williams)",        "target_pct": 0.6},
            {"key": "alonso",     "label": "🇪🇸 Fernando Alonso (Aston Martin)", "target_pct": 0.8},
            {"key": "lawson",     "label": "🇳🇿 Liam Lawson (Racing Bulls)",     "target_pct": 0.5},
            {"key": "lindblad",   "label": "🇬🇧 Arvid Lindblad (Racing Bulls)",  "target_pct": 0.5},
            {"key": "gasly",      "label": "🇫🇷 Pierre Gasly (Alpine)",          "target_pct": 0.5},
            {"key": "albon",      "label": "🇹🇭 Alexander Albon (Williams)",     "target_pct": 0.5},
            {"key": "hulkenberg", "label": "🇩🇪 Nico Hülkenberg (Audi)",         "target_pct": 0.4},
            {"key": "bortoleto",  "label": "🇧🇷 Gabriel Bortoleto (Audi)",       "target_pct": 0.4},
            {"key": "colapinto",  "label": "🇦🇷 Franco Colapinto (Alpine)",      "target_pct": 0.3},
            {"key": "bearman",    "label": "🇬🇧 Oliver Bearman (Haas)",          "target_pct": 0.3},
            {"key": "perez",      "label": "🇲🇽 Sergio Pérez (Cadillac)",        "target_pct": 0.3},
            {"key": "bottas",     "label": "🇫🇮 Valtteri Bottas (Cadillac)",     "target_pct": 0.3},
            {"key": "ocon",       "label": "🇫🇷 Esteban Ocon (Haas)",            "target_pct": 0.2},
            {"key": "stroll",     "label": "🇨🇦 Lance Stroll (Aston Martin)",    "target_pct": 0.2},
        ],
    },
    {
        "id": "f1-paisesbajos-2026-escuderia-ganadora",
        "question": "¿Qué escudería tendrá al piloto ganador del GP de Países Bajos 2026?",
        "description": (
            "Escudería del ganador de la carrera principal del GP de Países Bajos 2026 "
            "en Zandvoort, domingo 23 de agosto. El Sprint del sábado NO forma parte "
            "de este mercado."
        ),
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": (
            "Escudería del piloto clasificado oficialmente en primer lugar de la "
            "carrera principal según la clasificación oficial de la FIA publicada en "
            "formula1.com, incluyendo penalizaciones aplicadas el mismo día. Un piloto "
            "sustituto cuenta para su escudería. Si la carrera se cancela, el mercado "
            "se cancela."
        ),
        "ends_at": "2026-08-23T10:00:00Z",
        "b": 100.0,
        "trending": True,
        "market_type": "multi",
        "outcomes": [
            {"key": "mercedes",    "label": "⚫ Mercedes",        "target_pct": 44.0},
            {"key": "ferrari",     "label": "🔴 Ferrari",         "target_pct": 23.0},
            {"key": "mclaren",     "label": "🟠 McLaren",         "target_pct": 17.0},
            {"key": "redbull",     "label": "🔵 Red Bull Racing", "target_pct": 10.2},
            {"key": "williams",    "label": "💠 Williams",        "target_pct": 1.1},
            {"key": "racingbulls", "label": "🟣 Racing Bulls",    "target_pct": 1.0},
            {"key": "astonmartin", "label": "🟢 Aston Martin",    "target_pct": 1.0},
            {"key": "alpine",      "label": "🩵 Alpine",          "target_pct": 0.8},
            {"key": "audi",        "label": "⚙️ Audi",            "target_pct": 0.8},
            {"key": "cadillac",    "label": "🦅 Cadillac",        "target_pct": 0.6},
            {"key": "haas",        "label": "⚪ Haas",            "target_pct": 0.5},
        ],
    },
]


def init_qs_for_targets(targets: dict[str, float], b: float) -> dict[str, float]:
    """
    Return q_dict such that prices_multi(q_dict, b) ≈ targets (percentages summing to 100).
    Formula: q_i = b * log(p_i) + constant  — constant cancels in the softmax.
    We set q_i = b * log(p_i / p_ref) where p_ref = 1/N (uniform).
    (Mirrored verbatim from seed-markets-2026-06-23-multi.py.)
    """
    n = len(targets)
    p_ref = 1.0 / n  # uniform probability
    q = {}
    for key, pct in targets.items():
        p = pct / 100.0
        q[key] = b * math.log(p / p_ref)
    return q


async def main() -> None:
    inserted = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        for data in MARKETS:
            total_pct = sum(o["target_pct"] for o in data["outcomes"])
            if abs(total_pct - 100) >= 0.01:
                print(f"  WARNING {data['id']}: las pct suman {total_pct}, no 100")

            result = await db.execute(select(Market).where(Market.id == data["id"]))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {data['id']} (already exists)")
                skipped += 1
                continue

            b = data["b"]
            ends_at = datetime.fromisoformat(data["ends_at"].replace("Z", "+00:00"))

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
                print(f"    outcome: {o['label']:36s}  target={o['target_pct']:.1f}%  actual={initial_prices[key]:.2f}%")

            db.add(PriceHistory(market_id=market.id, yes_price=0.0, volume_snapshot=0.0))

            inserted += 1
            print(f"  INSERT {data['id']} (multi, b={b}, {len(data['outcomes'])} opciones)")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MARKETS)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
