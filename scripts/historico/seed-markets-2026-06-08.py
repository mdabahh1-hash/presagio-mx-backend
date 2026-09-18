"""
Seed script: 5 new markets for 2026-06-08
Run from the backend directory: python seed-markets-2026-06-08.py
"""
import asyncio
import sys
import os

# Make sure the app package is importable when running from the backend root
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr


NEW_MARKETS = [
    {
        "id": "mexico-sudafrica-gana-mundial-2026",
        "question": "¿Ganará México su partido inaugural contra Sudáfrica el 11 de junio?",
        "description": (
            "México debuta en el Mundial 2026 como local en el Estadio Ciudad de México "
            "contra Sudáfrica el 11 de junio a las 13:00h. Es el partido inaugural del torneo."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "El mercado resuelve YES si México marca más goles que Sudáfrica al final de los "
            "90 minutos reglamentarios el 11 de junio de 2026."
        ),
        "ends_at": "2026-06-11T20:00:00+00:00",
        "b": 200.0,
        "initial_yes_price": 50.0,
        "trending": True,
    },
    {
        "id": "mexico-avanza-fase-grupos-mundial26",
        "question": "¿Avanzará México a la siguiente ronda del Mundial 2026 desde el Grupo A?",
        "description": (
            "México enfrenta a Sudáfrica (11 jun), Corea del Sur (17 jun) y Chequia (24 jun) "
            "en el Grupo A del Mundial 2026 como local."
        ),
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": (
            "El mercado resuelve YES si México clasifica entre los dos primeros de su grupo "
            "o como mejor tercero, antes del 26 de junio de 2026."
        ),
        "ends_at": "2026-06-26T23:59:00+00:00",
        "b": 200.0,
        "initial_yes_price": 50.0,
        "trending": True,
    },
    {
        "id": "tmec-renovacion-antes-julio-2026",
        "question": "¿Se llegará a un acuerdo de renovación del T-MEC antes del 1 de julio de 2026?",
        "description": (
            "México, EE.UU. y Canadá tienen hasta el 1 de julio para renovar el T-MEC. "
            "EE.UU. propuso nuevos aranceles del 10% a México y Canadá por preocupaciones "
            "de trabajo forzoso."
        ),
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": (
            "El mercado resuelve YES si los tres países anuncian oficialmente un acuerdo de "
            "renovación o extensión del T-MEC antes del 1 de julio de 2026."
        ),
        "ends_at": "2026-07-01T18:00:00+00:00",
        "b": 200.0,
        "initial_yes_price": 50.0,
        "trending": True,
    },
    {
        "id": "banxico-recorte-tasa-2026-q3",
        "question": "¿Recortará Banxico la tasa de interés en alguna reunión del tercer trimestre de 2026?",
        "description": (
            "Banxico cerró su ciclo de recortes en mayo con tasa en 6.50%. La OCDE revisó a "
            "la baja el crecimiento de México a 0.8% para 2026."
        ),
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": (
            "El mercado resuelve YES si Banxico anuncia un recorte a la tasa de referencia "
            "en cualquiera de sus reuniones entre julio y septiembre de 2026."
        ),
        "ends_at": "2026-09-30T23:59:00+00:00",
        "b": 100.0,
        "initial_yes_price": 50.0,
        "trending": False,
    },
    {
        "id": "piojo-herrera-regresa-liga-mx-2026",
        "question": "¿Firmará Miguel 'Piojo' Herrera como DT en Liga MX antes del Apertura 2026?",
        "description": (
            "Reportes señalan que el Piojo estaría muy cerca de volver a Liga MX "
            "tras su etapa como seleccionador de Costa Rica."
        ),
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": (
            "El mercado resuelve YES si se anuncia oficialmente que Miguel Herrera firmó "
            "contrato con algún club de Liga MX antes del 25 de julio de 2026."
        ),
        "ends_at": "2026-07-25T23:59:00+00:00",
        "b": 100.0,
        "initial_yes_price": 50.0,
        "trending": False,
    },
]


async def main() -> None:
    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        for data in NEW_MARKETS:
            # Check if already exists
            result = await db.execute(select(Market).where(Market.id == data["id"]))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {data['id']}")
                skipped += 1
                continue

            # Compute LMSR initial state from the target price
            initial_price = data["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, data["b"])
            computed_yes_price = lmsr.yes_price_pct(q_yes, q_no, data["b"])

            # Parse ends_at
            from datetime import datetime, timezone
            ends_at = datetime.fromisoformat(data["ends_at"])

            market = Market(
                id=data["id"],
                question=data["question"],
                description=data["description"],
                category=data["category"],
                resolution_criteria=data["resolution_criteria"],
                ends_at=ends_at,
                b=data["b"],
                q_yes=q_yes,
                q_no=q_no,
                yes_price=computed_yes_price,
                status=MarketStatus.OPEN,
                trending=data.get("trending", False),
            )
            db.add(market)

            # Seed initial price history point
            db.add(PriceHistory(
                market_id=market.id,
                yes_price=computed_yes_price,
                volume_snapshot=0.0,
            ))

            print(f"  INSERT {data['id']}  (yes_price={computed_yes_price:.1f}%, b={data['b']})")
            inserted += 1

        await db.commit()

    print(f"\nDone. {inserted} inserted, {skipped} skipped.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
