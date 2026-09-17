"""Agregados de una categoría para su landing (riel de ligas y "Volumen por liga"
de Deportes). Sin tablas nuevas: `markets.volume` (acumulado por trade, todos los
estatus) y `trades.cost` en ventana para el volumen reciente.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market, MarketCategory, MarketStatus
from app.models.trade import Trade

VENTANA_DIAS = 7


async def resumen_categoria(db: AsyncSession, categoria: MarketCategory,
                            dias: int = VENTANA_DIAS) -> dict:
    """{categoria, abiertos, volumen_total, volumen_7d, subcategorias: [...]}.

    `subcategorias` va por volumen total desc (luego abiertos desc, luego nombre) y
    omite las filas sin subcategoría; los totales de la categoría sí las incluyen.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=dias)

    abiertos = func.count(Market.id).filter(Market.status == MarketStatus.OPEN)
    res = await db.execute(
        select(Market.subcategory, abiertos.label("abiertos"),
               func.coalesce(func.sum(Market.volume), 0.0).label("volumen_total"))
        .where(Market.category == categoria)
        .group_by(Market.subcategory)
    )
    filas = {sub: (int(n), float(vol)) for sub, n, vol in res.all()}

    res = await db.execute(
        select(Market.subcategory, func.coalesce(func.sum(Trade.cost), 0.0))
        .join(Market, Market.id == Trade.market_id)
        .where(Market.category == categoria)
        .where(Trade.created_at >= cutoff)
        .group_by(Market.subcategory)
    )
    reciente = {sub: float(vol) for sub, vol in res.all()}

    subcategorias = [
        {"subcategory": sub, "abiertos": n, "volumen_total": vol, "volumen_7d": reciente.get(sub, 0.0)}
        for sub, (n, vol) in filas.items() if sub
    ]
    subcategorias.sort(key=lambda d: (-d["volumen_total"], -d["abiertos"], d["subcategory"]))
    return {
        "categoria": categoria,
        "abiertos": sum(n for n, _ in filas.values()),
        "volumen_total": sum(vol for _, vol in filas.values()),
        "volumen_7d": sum(reciente.values()),
        "subcategorias": subcategorias,
    }
