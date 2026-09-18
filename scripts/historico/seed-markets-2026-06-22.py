"""
Seed script: 7 new markets for 2026-06-22
Run from the backend directory:
  DATABASE_URL="postgresql+asyncpg://..." python seed-markets-2026-06-22.py
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr


NEW_MARKETS = [
    {
        "id": "mundial-mexico-chequia-jun26",
        "question": "¿México le ganará a Chequia el 24 de junio?",
        "description": (
            "México cierra fase de grupos contra Chequia ya clasificado como líder del Grupo A. "
            "Aguirre podría rotar jugadores, lo que abre incertidumbre real sobre el resultado."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "Resuelve YES si México gana en tiempo reglamentario el partido del 24 de junio 2026. "
            "Empate o derrota resuelve NO. No aplica desempate porque es fase de grupos."
        ),
        "ends_at": "2026-06-25T01:00:00+00:00",
        "b": 200.0,
        "trending": True,
    },
    {
        "id": "mundial-mexico-cuartos-2026",
        "question": "¿México llegará a Cuartos de Final del Mundial?",
        "description": (
            "La maldición del quinto partido. México no ha pasado de Octavos en mundiales recientes. "
            "Llegar a Cuartos sería romper la barrera histórica."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "Resuelve YES si México clasifica a los Cuartos de Final del Mundial 2026. "
            "Se resolverá manualmente después del partido de Octavos de Final. "
            "Eliminación en Octavos o antes resuelve NO."
        ),
        "ends_at": "2026-07-11T05:00:00+00:00",
        "b": 200.0,
        "trending": True,
    },
    {
        "id": "mundial-brasil-campeon-2026",
        "question": "¿Brasil ganará el Mundial 2026?",
        "description": (
            "Brasil arrancó en el Grupo C pero los mercados lo ubican como uno de los menos "
            "favoritos para ganar el torneo. La final se juega el 19 de julio."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "Resuelve YES si Brasil es campeón del Mundial 2026. "
            "Cualquier otro campeón resuelve NO."
        ),
        "ends_at": "2026-07-19T22:00:00+00:00",
        "b": 200.0,
        "trending": True,
        # Opening price ~6% to match Polymarket. With b=200: q_no=550 gives yes_price≈6%.
        "q_yes_override": 0.0,
        "q_no_override": 550.0,
    },
    {
        "id": "banxico-tasa-junio-2026",
        "question": "¿Banxico mantendrá la tasa en 6.50% el 25 de junio?",
        "description": (
            "Banxico cerró su ciclo de recortes en mayo con la tasa en 6.50%. "
            "Su guía prospectiva apunta a mantener, pero la junta vota dividida "
            "y hay incertidumbre real."
        ),
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": (
            "Resuelve YES si el anuncio del 25 de junio 2026 deja la tasa objetivo en 6.50%. "
            "Cualquier movimiento (recorte o alza) resuelve NO."
        ),
        "ends_at": "2026-06-25T19:00:00+00:00",
        "b": 200.0,
        "trending": True,
    },
    {
        "id": "inflacion-1q-junio-2026",
        "question": "¿La inflación anual de la 1a quincena de junio será mayor a 4%?",
        "description": (
            "El INEGI publica el 24 de junio el INPC de la primera quincena de junio 2026. "
            "En mayo la inflación general cerró en 3.94% anual, justo en la frontera."
        ),
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": (
            "Resuelve YES si la inflación general anual de la primera quincena de junio 2026 "
            "publicada por INEGI es estrictamente mayor a 4.00%. Igual o menor resuelve NO."
        ),
        "ends_at": "2026-06-24T14:00:00+00:00",
        "b": 100.0,
        "trending": False,
    },
    {
        "id": "bitcoin-70k-julio-2026",
        "question": "¿Bitcoin superará los 70,000 USD antes del 15 de julio?",
        "description": (
            "Bitcoin cotiza alrededor de 65,000 USD el 22 de junio, presionado a la baja "
            "tras la última decisión de la Fed que descartó recortes en 2026."
        ),
        "category": MarketCategory.CRYPTO,
        "resolution_criteria": (
            "Resuelve YES si el precio de BTC/USD toca o supera 70,000 en cualquier momento "
            "antes del 15 de julio 2026 a las 00:00 hora CDMX, según CoinGecko. "
            "Si no lo alcanza, resuelve NO."
        ),
        "ends_at": "2026-07-15T05:00:00+00:00",
        "b": 100.0,
        "trending": False,
    },
    {
        "id": "usdmxn-cierre-junio-2026",
        "question": "¿El dólar cerrará junio por encima de 17.80 pesos?",
        "description": (
            "El FIX de Banxico del 22 de junio se ubica en 17.3480. Una depreciación hasta 17.80 "
            "implicaría un movimiento de más de 45 centavos en los últimos días hábiles de junio."
        ),
        "category": MarketCategory.MERCADOS_GLOBALES,
        "resolution_criteria": (
            "Resuelve YES si el tipo de cambio FIX publicado por Banxico del último día hábil "
            "de junio 2026 (30 de junio) es estrictamente mayor a 17.80 MXN por USD. "
            "Igual o menor resuelve NO."
        ),
        "ends_at": "2026-07-01T00:00:00+00:00",
        "b": 100.0,
        "trending": False,
    },
]


async def main() -> None:
    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        for data in NEW_MARKETS:
            result = await db.execute(select(Market).where(Market.id == data["id"]))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {data['id']}")
                skipped += 1
                continue

            b = data["b"]
            ends_at = datetime.fromisoformat(data["ends_at"])

            # Brazil opens at ~6%: use explicit q overrides instead of init_q_for_price
            if "q_yes_override" in data:
                q_yes = data["q_yes_override"]
                q_no = data["q_no_override"]
            else:
                # All other markets open at 50%: LMSR is symmetric at origin
                q_yes = 0.0
                q_no = 0.0

            yes_price = lmsr.yes_price_pct(q_yes, q_no, b)

            market = Market(
                id=data["id"],
                question=data["question"],
                description=data["description"],
                category=data["category"],
                resolution_criteria=data["resolution_criteria"],
                ends_at=ends_at,
                b=b,
                q_yes=q_yes,
                q_no=q_no,
                yes_price=yes_price,
                status=MarketStatus.OPEN,
                trending=data.get("trending", False),
            )
            db.add(market)

            db.add(PriceHistory(
                market_id=market.id,
                yes_price=yes_price,
                volume_snapshot=0.0,
            ))

            print(f"  INSERT {data['id']}  (yes_price={yes_price:.1f}%, b={b})")
            inserted += 1

        await db.commit()

    print(f"\nDone. {inserted} inserted, {skipped} skipped.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
