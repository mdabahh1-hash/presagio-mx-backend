"""Seed BINARY markets (2026-06-26 v3).

Mirrors app/services/seed.py: derives the LMSR opening state from each market's
initial_yes_price via app.core.lmsr, inserts the markets row + one price_history
row, and is idempotent (SELECT by id, skip if it already exists — no ON CONFLICT).

Run against the target database, e.g.:
    DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:PORT/DB" \
        python seed-markets-2026-06-26-v3.py
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr


MARKETS = [
    {
        "id": "mundial-mexico-semifinal-2026",
        "question": "¿México llega a semifinales del Mundial 2026?",
        "description": "Tras ganar el Grupo A con paso perfecto, México debe encadenar dieciseisavos, octavos y cuartos para llegar a semifinales. Son tres triunfos seguidos de eliminación directa.",
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": "Resuelve SÍ si México llega a semifinales del Mundial 2026. Resuelve NO si es eliminada antes. Fuente que decide, cuadro oficial FIFA.",
        "ends_at": datetime(2026, 7, 15, 6, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 22.0,
        "trending": True,
    },
    {
        "id": "f1-checo-puntos-austria-2026",
        "question": "¿Checo Pérez termina en zona de puntos en el GP de Austria 2026?",
        "description": "Cadillac llega sin sumar puntos en toda la temporada y su mejor resultado es P14. Checo corre el GP de Austria el 28 de junio en el Red Bull Ring, una pista corta donde el equipo espera mejorar.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si Checo Pérez termina entre los 10 primeros (zona de puntos) en el GP de Austria 2026. Resuelve NO si termina 11o o peor, no clasifica o no termina. Fuente que decide, resultado oficial FIA.",
        "ends_at": datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 18.0,
        "trending": True,
    },
    {
        "id": "btc-cierra-bajo-60k-30jun26",
        "question": "¿Bitcoin cierra por debajo de 60,000 USD el 30 de junio de 2026?",
        "description": "BTC rompió el soporte de 60,000 y cotiza cerca de 59,700, en mínimos de 2026 con momentum bajista. Está justo sobre la línea hacia el cierre de mes.",
        "category": MarketCategory.CRYPTO,
        "resolution_criteria": "Resuelve SÍ si el precio de cierre diario de BTC/USD del 30 jun 2026 (23:59 UTC) es menor a 60,000 USD. Resuelve NO si es 60,000 o mayor. Fuente que decide, CoinGecko.",
        "ends_at": datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 58.0,
        "trending": True,
    },
    {
        "id": "inflacion-inegi-junio-baja-2026",
        "question": "¿La inflación anual de junio 2026 (INEGI) baja respecto a mayo?",
        "description": "La inflación general anual de mayo fue 3.94%. La primera quincena de junio salió en 3.55%, sexta quincena consecutiva a la baja. El dato mensual lo publica INEGI a inicios de julio.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si la inflación general anual de junio 2026 (INPC mensual, INEGI) es menor que la de mayo 2026 (3.94%). Resuelve NO si es igual o mayor. Fuente que decide, INEGI.",
        "ends_at": datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 80.0,
        "trending": False,
    },
    {
        "id": "odisea-nolan-debut-100m-2026",
        "question": "¿La Odisea de Nolan debuta con más de 100M USD en EE.UU.?",
        "description": "La Odisea de Christopher Nolan, rodada íntegramente en IMAX con presupuesto de 250M, estrena el 17 de julio. Oppenheimer abrió en 82M, así que un debut sobre 100M es exigente pero posible por el hype.",
        "category": MarketCategory.ENTRETENIMIENTO,
        "resolution_criteria": "Resuelve SÍ si la recaudación del fin de semana de estreno doméstico (EE.UU., 3 días) supera 100M USD. Resuelve NO si es 100M o menos. Fuente que decide, Box Office Mojo.",
        "ends_at": datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 38.0,
        "trending": False,
    },
    {
        "id": "usdmxn-cierra-bajo-1750-jul26",
        "question": "¿El dólar (USD/MXN) cierra julio 2026 por debajo de 17.50 pesos?",
        "description": "El peso cotiza fuerte cerca de 17.48 por dólar, sostenido por el carry trade tras la pausa de Banxico en 6.50%. La revisión del T-MEC es el principal riesgo de depreciación en las próximas semanas.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si el tipo de cambio USD/MXN al cierre del 31 jul 2026 es menor a 17.50 pesos por dólar. Resuelve NO si es 17.50 o mayor. Fuente que decide, FIX de Banxico del último día hábil de julio.",
        "ends_at": datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 48.0,
        "trending": False,
    },
    {
        "id": "pib-mexico-2t-crece-2026",
        "question": "¿El PIB de México del 2T 2026 crece respecto al 1T?",
        "description": "El PIB del 1T 2026 se contrajo 0.8%, la mayor caída desde finales de 2024. El gobierno presume un rebote de la construcción y del empleo manufacturero en el segundo semestre. INEGI publica la estimación oportuna a fin de julio.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si la estimación oportuna del PIB del 2T 2026 (INEGI) muestra variación trimestral positiva respecto al 1T 2026. Resuelve NO si es cero o negativa. Fuente que decide, INEGI.",
        "ends_at": datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 55.0,
        "trending": False,
    },
    {
        "id": "spiderman-debut-150m-2026",
        "question": "¿Spider-Man Brand New Day debuta con más de 150M USD en EE.UU.?",
        "description": "La nueva entrega de Spider-Man con Tom Holland estrena el 31 de julio y apunta cerca de 900M mundiales. Las aperturas domésticas del personaje suelen ser enormes.",
        "category": MarketCategory.ENTRETENIMIENTO,
        "resolution_criteria": "Resuelve SÍ si la recaudación del fin de semana de estreno doméstico (EE.UU., 3 días) supera 150M USD. Resuelve NO si es 150M o menos. Fuente que decide, Box Office Mojo.",
        "ends_at": datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 55.0,
        "trending": False,
    },
    {
        "id": "btc-toca-55k-antes-ago-2026",
        "question": "¿Bitcoin toca 55,000 USD o menos antes del 1 de agosto de 2026?",
        "description": "Con BTC cerca de 59,700 y estructura bajista, los siguientes soportes están en 58,200 y luego 55,000. En Polymarket dan ~55% a que caiga por debajo de 55,000 antes de cerrar 2026; en ventana corta la probabilidad baja.",
        "category": MarketCategory.CRYPTO,
        "resolution_criteria": "Resuelve SÍ si BTC/USD cotiza en 55,000 USD o menos en cualquier momento entre la creación del mercado y el 31 jul 2026 (23:59 UTC). Resuelve NO si no toca ese nivel. Fuente que decide, precio spot CoinGecko.",
        "ends_at": datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 40.0,
        "trending": False,
    },
    {
        "id": "eeuu-iran-acuerdo-final-2026",
        "question": "¿EE.UU. e Irán firman el acuerdo final de paz antes del 18 de agosto de 2026?",
        "description": "El 18 de junio se anunció una tregua de 60 días con una hoja de ruta para un pacto final. Todavía hay ataques aislados a buques en el estrecho de Ormuz, lo que mantiene la duda sobre si se firma a tiempo.",
        "category": MarketCategory.GLOBAL,
        "resolution_criteria": "Resuelve SÍ si EE.UU. e Irán firman un acuerdo o memorando final de paz antes del 18 ago 2026 (23:00 UTC). Resuelve NO si no se firma para esa fecha. Fuente que decide, comunicado oficial de las partes o de los mediadores.",
        "ends_at": datetime(2026, 8, 18, 0, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
    {
        "id": "anthropic-ipo-2026",
        "question": "¿Anthropic sale a bolsa (IPO) antes del 31 de diciembre de 2026?",
        "description": "Anthropic, creador de Claude, presentó de forma confidencial su solicitud de IPO a inicios de junio 2026 y su valuación privada saltó de 380 a 965 mil millones de dólares entre febrero y mayo. Va camino a su primer trimestre con utilidad operativa, mientras SpaceX abrió la fila de salidas de IA y OpenAI también señaló debut en 2026.",
        "category": MarketCategory.TECH,
        "resolution_criteria": "Resuelve SÍ si las acciones de Anthropic comienzan a cotizar en una bolsa de EE.UU. (NYSE o Nasdaq) en cualquier momento antes del 31 dic 2026 (23:59 ET). Resuelve NO si para esa fecha no ha debutado. Fuente que decide, comunicado oficial de la empresa o de la bolsa.",
        "ends_at": datetime(2027, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 62.0,
        "trending": True,
    },
    {
        "id": "openai-ipo-2026",
        "question": "¿OpenAI sale a bolsa (IPO) antes del 31 de diciembre de 2026?",
        "description": "OpenAI, creador de ChatGPT, anunció planes de salir a bolsa después de que Anthropic filtrara su solicitud, pero va más atrás en el proceso, en etapa pre-filing o confidencial. Levantó 122 mil millones en marzo con valuación de 852 mil millones de dólares y genera cerca de 2 mil millones de ingresos al mes.",
        "category": MarketCategory.TECH,
        "resolution_criteria": "Resuelve SÍ si las acciones de OpenAI comienzan a cotizar en una bolsa de EE.UU. (NYSE o Nasdaq) en cualquier momento antes del 31 dic 2026 (23:59 ET). Resuelve NO si para esa fecha no ha debutado. Fuente que decide, comunicado oficial de la empresa o de la bolsa.",
        "ends_at": datetime(2027, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 52.0,
        "trending": True,
    },
]


async def main() -> None:
    inserted = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        for data in MARKETS:
            exists = await db.execute(select(Market).where(Market.id == data["id"]))
            if exists.scalar_one_or_none():
                print(f"SKIP  {data['id']} (ya existe)")
                skipped += 1
                continue

            initial_price = data["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, data["b"])
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, data["b"])

            market = Market(
                id=data["id"],
                question=data["question"],
                description=data["description"],
                category=data["category"],
                resolution_criteria=data["resolution_criteria"],
                ends_at=data["ends_at"],
                b=data["b"],
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
            db.add(PriceHistory(
                market_id=market.id,
                yes_price=yes_price_val,
                volume_snapshot=0.0,
            ))
            print(f"INSERT {data['id']}  yes_price={yes_price_val}  b={data['b']}")
            inserted += 1

        await db.commit()

    print(f"\nListo. Insertados: {inserted}  |  Saltados: {skipped}  |  Total: {len(MARKETS)}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
