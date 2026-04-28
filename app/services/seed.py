"""Seed the database with initial markets on first run."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr

SEED_MARKETS = [
    {
        "id": "morena-2027",
        "question": "¿Ganará Morena las elecciones intermedias de 2027?",
        "description": "Este mercado resuelve SÍ si el partido Morena obtiene la mayoría absoluta en la Cámara de Diputados en las elecciones intermedias de 2027. Resolución basada en resultados oficiales del INE.",
        "category": MarketCategory.POLITICA_MX,
        "resolution_criteria": "Resuelve SÍ si Morena + aliados obtienen más de 251 diputaciones según resultados definitivos del INE.",
        "ends_at": datetime(2027, 6, 6, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 72.0,
        "trending": True,
    },
    {
        "id": "dolar-22",
        "question": "¿Subirá el dólar a más de $22 MXN antes del 1 de julio de 2026?",
        "description": "Mercado sobre el tipo de cambio USD/MXN. Resuelve SÍ si el tipo de cambio spot alcanza o supera $22.00 pesos por dólar en cualquier día hábil antes del 1 de julio de 2026, según datos de Banxico.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si el tipo de cambio FIX de Banxico alcanza ≥ $22.00 en cualquier sesión antes del 1 Jul 2026.",
        "ends_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 34.0,
        "trending": True,
    },
    {
        "id": "mexico-mundial",
        "question": "¿Clasificará México directamente al Mundial 2026?",
        "description": "Resuelve SÍ si la selección mexicana clasifica directamente (sin repechaje) al Mundial FIFA 2026. CONCACAF otorga 3 cupos directos y 1 de repechaje.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si México termina entre los primeros 3 de la fase final de CONCACAF.",
        "ends_at": datetime(2026, 3, 25, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 88.0,
        "trending": True,
    },
    {
        "id": "banxico-tasa",
        "question": "¿Bajará Banxico la tasa a menos de 8% antes de diciembre 2026?",
        "description": "Resuelve SÍ si la Junta de Gobierno de Banxico vota una tasa objetivo del Fondeo Bancario por debajo de 8.00% en cualquier reunión antes del 18 de diciembre de 2026.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Basado en comunicados oficiales de Banxico tras cada reunión de política monetaria.",
        "ends_at": datetime(2026, 12, 18, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 61.0,
        "trending": False,
    },
    {
        "id": "fed-recorte",
        "question": "¿Recortará la Fed las tasas antes de septiembre 2026?",
        "description": "Resuelve SÍ si la Reserva Federal de EE.UU. reduce el rango objetivo de fondos federales en al menos 25 puntos base en cualquier reunión del FOMC antes del 1 de septiembre de 2026.",
        "category": MarketCategory.GLOBAL,
        "resolution_criteria": "Basado en comunicados oficiales del FOMC.",
        "ends_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "b": 200.0,
        "initial_yes_price": 55.0,
        "trending": True,
    },
    {
        "id": "bitcoin-100k",
        "question": "¿Superará Bitcoin los $100,000 USD antes de junio 2026?",
        "description": "Resuelve SÍ si el precio de Bitcoin supera los $100,000 USD en cualquier exchange mayor (Binance, Coinbase) antes del 1 de junio de 2026.",
        "category": MarketCategory.TECH,
        "resolution_criteria": "Precio basado en promedio de Binance y Coinbase Pro.",
        "ends_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "b": 200.0,
        "initial_yes_price": 67.0,
        "trending": True,
    },
    {
        "id": "nvidia-1000",
        "question": "¿Superará NVIDIA los $1,000 USD por acción en 2026?",
        "description": "Resuelve SÍ si el precio de cierre de NVDA en NASDAQ supera los $1,000 USD en cualquier sesión durante el año 2026.",
        "category": MarketCategory.TECH,
        "resolution_criteria": "Basado en precio de cierre oficial de NASDAQ.",
        "ends_at": datetime(2026, 12, 31, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 42.0,
        "trending": False,
    },
    {
        "id": "cdmx-alcalde",
        "question": "¿Ganará oposición la jefatura de gobierno de CDMX en 2027?",
        "description": "Resuelve SÍ si un candidato de la oposición (distinto a Morena y aliados) gana la Jefatura de Gobierno de la Ciudad de México en las elecciones de 2027.",
        "category": MarketCategory.POLITICA_MX,
        "resolution_criteria": "Basado en resultados definitivos del INE/IECM.",
        "ends_at": datetime(2027, 6, 6, tzinfo=timezone.utc),
        "b": 80.0,
        "initial_yes_price": 28.0,
        "trending": False,
    },
    {
        "id": "tigres-champions",
        "question": "¿Llegará un equipo mexicano a la final de la CONCACAF Champions Cup 2026?",
        "description": "Resuelve SÍ si al menos un club mexicano (Liga MX) llega a la final de la CONCACAF Champions Cup 2026.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Basado en resultados oficiales de CONCACAF.",
        "ends_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
        "b": 80.0,
        "initial_yes_price": 79.0,
        "trending": False,
    },
    {
        "id": "xochitl-2030",
        "question": "¿Será Xóchitl Gálvez candidata presidencial en 2030?",
        "description": "Resuelve SÍ si Xóchitl Gálvez es registrada formalmente como candidata presidencial por cualquier partido o coalición para las elecciones de 2030.",
        "category": MarketCategory.POLITICA_MX,
        "resolution_criteria": "Resolución basada en registro oficial ante el INE.",
        "ends_at": datetime(2030, 1, 15, tzinfo=timezone.utc),
        "b": 80.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
]


async def seed_markets() -> None:
    async with AsyncSessionLocal() as db:
        for data in SEED_MARKETS:
            exists = await db.execute(select(Market).where(Market.id == data["id"]))
            if exists.scalar_one_or_none():
                continue

            initial_price = data["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, data["b"])

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
                yes_price=lmsr.yes_price_pct(q_yes, q_no, data["b"]),
                status=MarketStatus.OPEN,
                trending=data.get("trending", False),
            )
            db.add(market)
            db.add(PriceHistory(
                market_id=market.id,
                yes_price=market.yes_price,
                volume_snapshot=0.0,
            ))
        await db.commit()
