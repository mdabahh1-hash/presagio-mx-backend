"""
Seed script: 8 new binary markets for 2026-08-17
(Banxico/Fed septiembre, Checo en Zandvoort, Leagues Cup, FIX y quincena de inflación)

Run from the backend directory:
  DATABASE_URL="postgresql+asyncpg://..." python seed-markets-2026-08-17.py
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr


MARKETS = [
    {
        "id": "banxico-mantiene-tasa-sep26",
        "question": "¿Banxico mantiene la tasa de referencia en 6.50% en su decisión del 24 de septiembre de 2026?",
        "description": "Tras el recorte de marzo, Banxico ha mantenido la tasa en 6.50% en sus últimas tres decisiones y su comunicado señala que será apropiado mantenerla en su nivel actual. La inflación bajó a 3.10% en la primera quincena de julio, su nivel más bajo desde 2020.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si el anuncio de política monetaria de Banxico del 24 de septiembre de 2026 deja la tasa objetivo en 6.50%. Resuelve NO ante cualquier movimiento al alza o a la baja. Fuente: comunicado oficial en banxico.org.mx.",
        "ends_at": datetime(2026, 9, 24, 18, 55, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 88.0,
        "trending": True,
    },
    {
        "id": "fed-mantiene-tasa-sep26",
        "question": "¿La Fed mantiene su tasa sin cambios en la decisión del 16 de septiembre de 2026?",
        "description": "El mercado venía de descontar un alza y giró tras el mal dato de empleo de julio y un CPI en línea. El escenario base de futuros es que la Fed no se mueva, pero la división interna del FOMC mantiene viva la incertidumbre.",
        "category": MarketCategory.MERCADOS_GLOBALES,
        "resolution_criteria": "Resuelve SÍ si el FOMC deja el rango objetivo de fed funds sin cambios en su anuncio del 16 de septiembre de 2026. Resuelve NO si sube o baja. Fuente: comunicado oficial de la Reserva Federal (federalreserve.gov).",
        "ends_at": datetime(2026, 9, 16, 17, 55, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 65.0,
        "trending": False,
    },
    {
        "id": "checo-puntos-gp-paises-bajos-26",
        "question": "¿Checo Pérez suma puntos en el GP de Países Bajos del 23 de agosto de 2026?",
        "description": "Checo regresa del receso de verano sin puntos en su primera temporada con Cadillac, con dos abandonos recientes y un mejor resultado de P15 tras sanción. Zandvoort estrena formato sprint y Cadillac llega con nuevo jefe de equipo.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si Sergio Pérez suma al menos un punto en el fin de semana del GP de Países Bajos 2026, ya sea en la carrera sprint del sábado o terminando en el top 10 de la carrera principal del domingo según la clasificación oficial de la FIA después de sanciones. Fuente: resultados oficiales FIA / formula1.com.",
        "ends_at": datetime(2026, 8, 22, 8, 55, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 12.0,
        "trending": True,
    },
    {
        "id": "liga-mx-gana-leagues-cup-26",
        "question": "¿Un equipo de la Liga MX gana la Leagues Cup 2026?",
        "description": "León, Toluca, Monterrey y América llegan a cuartos de final contra cuatro equipos de la MLS. La MLS ha ganado todas las ediciones oficiales del torneo y ningún club mexicano llegó a semifinales en las últimas dos ediciones. La final es el 6 de septiembre.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si el campeón de la Leagues Cup 2026 (final del 6 de septiembre) es un club de la Liga MX. Resuelve NO si el campeón es un club de la MLS. Fuente: resultado oficial publicado por Leagues Cup.",
        "ends_at": datetime(2026, 9, 6, 20, 0, 0, tzinfo=timezone.utc),
        "b": 200.0,
        "initial_yes_price": 40.0,
        "trending": True,
    },
    {
        "id": "monterrey-semis-leagues-cup-26",
        "question": "¿Monterrey elimina a Chicago Fire y avanza a semifinales de la Leagues Cup 2026?",
        "description": "Rayados visita al Chicago Fire, el mejor clasificado de la MLS, en partido único de cuartos de final entre el 25 y 27 de agosto. Si hay empate a los 90 minutos se define en penales.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si Monterrey avanza a semifinales de la Leagues Cup 2026 eliminando a Chicago Fire, en 90 minutos o en penales. Resuelve NO si Chicago Fire avanza. Fuente: resultado oficial de Leagues Cup.",
        "ends_at": datetime(2026, 8, 25, 0, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 55.0,
        "trending": False,
    },
    {
        "id": "america-semis-leagues-cup-26",
        "question": "¿América elimina a Columbus Crew y avanza a semifinales de la Leagues Cup 2026?",
        "description": "El América enfrenta al Columbus Crew en partido único de cuartos de final entre el 25 y 27 de agosto, con antecedente de la Campeones Cup 2024 entre ambos. Sin tiempo extra, empate a los 90 se define en penales.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si América avanza a semifinales de la Leagues Cup 2026 eliminando a Columbus Crew, en 90 minutos o en penales. Resuelve NO si Columbus avanza. Fuente: resultado oficial de Leagues Cup.",
        "ends_at": datetime(2026, 8, 25, 0, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
    {
        "id": "usdmxn-debajo-17-fix-28ago26",
        "question": "¿El tipo de cambio FIX de Banxico cierra por debajo de 17.00 pesos por dólar el viernes 28 de agosto de 2026?",
        "description": "El peso opera en su mejor nivel en más de dos años, alrededor de 17.02 por dólar, y esta semana llegó a tocar 16.985. La ruptura sostenida del piso de 17.00 es el tema cambiario del momento.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si el tipo de cambio FIX publicado por Banxico correspondiente al viernes 28 de agosto de 2026 es estrictamente menor a 17.0000 pesos por dólar. Resuelve NO si es igual o mayor. Fuente: serie FIX oficial en banxico.org.mx.",
        "ends_at": datetime(2026, 8, 28, 17, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 50.0,
        "trending": False,
    },
    {
        "id": "inflacion-1q-ago26-debajo-3",
        "question": "¿La inflación anual de la primera quincena de agosto de 2026 queda por debajo de 3.00%?",
        "description": "La inflación general bajó de 3.55% a 3.10% entre junio y la primera quincena de julio y se encamina a su nivel más bajo desde diciembre de 2020. El dato quincenal de agosto que publica INEGI dirá si por fin perfora el 3%.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si la variación anual del INPC de la primera quincena de agosto de 2026, publicada por INEGI, es estrictamente menor a 3.00%. Resuelve NO si es igual o mayor. Fuente: comunicado oficial de INEGI.",
        "ends_at": datetime(2026, 8, 24, 11, 55, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
]


async def main() -> None:
    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        for data in MARKETS:
            result = await db.execute(select(Market).where(Market.id == data["id"]))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {data['id']}")
                skipped += 1
                continue

            # Nunca sembrar un mercado ya cerrado: si fue borrado a propósito
            # (cleanup-mercados-vencidos-sin-predicciones-*), no debe resucitar.
            if data["ends_at"] < datetime.now(timezone.utc):
                print(f"  SKIP  {data['id']} (ya vencido: {data['ends_at']:%Y-%m-%d %H:%M} UTC; no se siembran mercados cerrados)")
                skipped += 1
                continue

            b = data["b"]
            initial_price = data["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, b)
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, b)

            market = Market(
                id=data["id"],
                question=data["question"],
                description=data["description"],
                category=data["category"],
                resolution_criteria=data["resolution_criteria"],
                ends_at=data["ends_at"],
                b=b,
                q_yes=q_yes,
                q_no=q_no,
                yes_price=yes_price_val,
                volume=0.0,
                num_trades=0,
                status=MarketStatus.OPEN,
                trending=data.get("trending", False),
                market_type="binary",
            )
            db.add(market)

            # Opening point for the chart (outcome_key omitted → NULL, correct for binary)
            db.add(PriceHistory(
                market_id=market.id,
                yes_price=yes_price_val,
                volume_snapshot=0.0,
            ))

            print(f"  INSERT {data['id']}  (yes_price={yes_price_val:.1f}%, b={b})")
            inserted += 1

        await db.commit()

    print(f"\nDone. {inserted} inserted, {skipped} skipped.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
