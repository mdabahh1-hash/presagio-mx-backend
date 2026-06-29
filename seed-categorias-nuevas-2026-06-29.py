"""Add new market categories (Clima, Boxeo, Motor) + seed markets in them.

IMPORTANT — this codebase stores the enum *NAME* (e.g. MUNDIAL_2026), not the
display value ("Mundial 2026"), in markets.category (verified against the live
DB). So the Postgres enum must gain the NAMES 'CLIMA' / 'BOXEO' / 'MOTOR'. The
display values are produced by the API serializer from the Python enum.

Order matters:
  PASO 2 — add enum values in their OWN committed (AUTOCOMMIT) transaction, then
           close that connection. A new enum value cannot be used in the same
           transaction that adds it.
  PASO 3 — seed markets in a fresh session, idempotent by id.

Run:
    DATABASE_URL="postgresql+asyncpg://..." python seed-categorias-nuevas-2026-06-29.py
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr

ENUM_TYPE = "marketcategory"
# The enum NAMES to ensure (NOT the display values).
NEW_CATEGORY_NAMES = ["CLIMA", "BOXEO", "MOTOR"]


MARKETS = [
    {
        "id": "huracan-mayor-toca-mexico-2026",
        "question": "¿Un huracán categoría 3 o mayor toca tierra en México en la temporada 2026?",
        "description": "El SMN pronostica una temporada activa en el Pacífico para 2026 con cuatro a cinco huracanes mayores, impulsada por El Niño y mares más cálidos. La temporada corre del 15 de mayo al 30 de noviembre.",
        "category": MarketCategory.CLIMA,
        "resolution_criteria": "Resuelve SÍ si al menos un huracán categoría 3, 4 o 5 en la escala Saffir-Simpson toca tierra en territorio mexicano entre el 15 de mayo y el 30 de noviembre de 2026. Fuente SMN Conagua y NHC.",
        "ends_at": datetime(2026, 12, 1, 6, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 70.0,
        "trending": False,
    },
    {
        "id": "huracan-pacifico-cat3-antes-ago-2026",
        "question": "¿Se forma un huracán categoría 3 o mayor en el Pacífico antes del 1 de agosto de 2026?",
        "description": "La temporada del Pacífico arrancó el 15 de mayo y el SMN la prevé por arriba del promedio. El mercado pregunta si un huracán mayor aparece temprano, antes de agosto.",
        "category": MarketCategory.CLIMA,
        "resolution_criteria": "Resuelve SÍ si en el Pacífico nororiental se forma al menos un huracán categoría 3 o superior antes del 1 de agosto de 2026. Fuente SMN y NHC.",
        "ends_at": datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 50.0,
        "trending": False,
    },
    {
        "id": "canelo-vence-mbilli-sep-2026",
        "question": "¿Canelo Álvarez vence a Christian Mbilli el 12 de septiembre de 2026?",
        "description": "Canelo regresa el 12 de septiembre en Riad ante el campeón WBC de supermedios Christian Mbilli, invicto. Es su primer combate tras perder con Crawford y una cirugía de codo.",
        "category": MarketCategory.BOXEO,
        "resolution_criteria": "Resuelve SÍ si Canelo derrota a Mbilli por decisión, nocaut o descalificación en su combate del 12 de septiembre de 2026. Empate o derrota resuelve NO. Fuente resultado oficial.",
        "ends_at": datetime(2026, 9, 13, 6, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 68.0,
        "trending": True,
    },
    {
        "id": "canelo-gana-por-nocaut-sep-2026",
        "question": "¿Canelo gana por nocaut o TKO a Mbilli?",
        "description": "Mercado derivado del mismo combate. Canelo no termina seguido por nocaut en sus últimas peleas y Mbilli llega invicto, así que ganar por la vía rápida es menos probable que ganar.",
        "category": MarketCategory.BOXEO,
        "resolution_criteria": "Resuelve SÍ si Canelo gana por KO, TKO o detención del árbitro o la esquina. Victoria por decisión, empate o derrota resuelve NO. Fuente resultado oficial.",
        "ends_at": datetime(2026, 9, 13, 6, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 28.0,
        "trending": False,
    },
    {
        "id": "checo-puntos-gp-mexico-2026",
        "question": "¿Checo Pérez suma puntos en el Gran Premio de México 2026?",
        "description": "Checo volvió a la F1 en 2026 con la nueva escudería Cadillac, un equipo debutante y poco competitivo que ya sumó varios abandonos. Corre en casa el 1 de noviembre ante su afición.",
        "category": MarketCategory.MOTOR,
        "resolution_criteria": "Resuelve SÍ si Checo Pérez termina entre los primeros 10 lugares en el Gran Premio de México 2026 del 1 de noviembre. Fuente FIA y resultados oficiales de F1.",
        "ends_at": datetime(2026, 11, 2, 6, 0, 0, tzinfo=timezone.utc),
        "b": 120.0,
        "initial_yes_price": 38.0,
        "trending": True,
    },
    {
        "id": "checo-top10-campeonato-2026",
        "question": "¿Checo Pérez termina la temporada 2026 dentro del top 10 del campeonato?",
        "description": "Cadillac es la escudería número 11 y debutante en 2026, con ritmo bajo y abandonos para Checo. La temporada cierra el 6 de diciembre en Abu Dabi y quedar entre los diez primeros es cuesta arriba.",
        "category": MarketCategory.MOTOR,
        "resolution_criteria": "Resuelve SÍ si Checo Pérez finaliza dentro de los primeros 10 del Campeonato Mundial de Pilotos 2026 al término de la temporada el 6 de diciembre. Fuente FIA.",
        "ends_at": datetime(2026, 12, 7, 6, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 30.0,
        "trending": False,
    },
]


async def migrate_enum() -> list[str]:
    """PASO 2 — add the new enum NAMES in their own AUTOCOMMIT connection.
    Returns the list of names that were actually added (not already present)."""
    ac_engine = create_async_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    added: list[str] = []
    try:
        async with ac_engine.connect() as conn:
            existing = set(
                (await conn.execute(text(
                    "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = :tn"
                ), {"tn": ENUM_TYPE})).scalars().all()
            )
            for name in NEW_CATEGORY_NAMES:
                await conn.execute(text(f"ALTER TYPE {ENUM_TYPE} ADD VALUE IF NOT EXISTS '{name}'"))
                if name not in existing:
                    added.append(name)
    finally:
        await ac_engine.dispose()
    return added


async def seed_markets() -> tuple[int, int]:
    """PASO 3 — seed the markets in a fresh session, idempotent by id."""
    inserted = skipped = 0
    async with AsyncSessionLocal() as db:
        for data in MARKETS:
            exists = (await db.execute(select(Market).where(Market.id == data["id"]))).scalar_one_or_none()
            if exists:
                print(f"SKIP   {data['id']} (ya existe)")
                skipped += 1
                continue
            p = data["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(p, data["b"])
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, data["b"])
            m = Market(
                id=data["id"], question=data["question"], description=data["description"],
                category=data["category"], resolution_criteria=data["resolution_criteria"],
                ends_at=data["ends_at"], b=data["b"], q_yes=q_yes, q_no=q_no,
                yes_price=yes_price_val, volume=0.0, num_trades=0,
                status=MarketStatus.OPEN, trending=data.get("trending", False), market_type="binary",
            )
            db.add(m)
            db.add(PriceHistory(market_id=m.id, yes_price=yes_price_val, volume_snapshot=0.0))
            print(f"INSERT {data['id']}  [{data['category'].value}]  yes_price={yes_price_val}  b={data['b']}")
            inserted += 1
        await db.commit()
    return inserted, skipped


async def main() -> None:
    print("══════════ PASO 2 — migrar enum marketcategory (AUTOCOMMIT) ══════════")
    added = await migrate_enum()
    for name in NEW_CATEGORY_NAMES:
        print(f"  {name}: {'AGREGADO' if name in added else 'ya existía'}")

    print("\n══════════ PASO 3 — sembrar mercados ══════════")
    inserted, skipped = await seed_markets()

    print("\n══════════ RESUMEN ══════════")
    print(f"Categorías agregadas: {len(added)} ({', '.join(added) if added else 'ninguna'})")
    print(f"Mercados insertados:  {inserted}")
    print(f"Mercados saltados:    {skipped}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
