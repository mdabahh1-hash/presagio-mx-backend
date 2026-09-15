"""Mercados que más se movieron en las últimas N horas (página "Noticias").

Se calcula desde `price_history`: una fila por operación (binarios con
`outcome_key` NULL; multi una fila por outcome). El seed de un multi deja una
fila placeholder `yes_price=0.0` sin `outcome_key`: se ignora. La línea base es
la última fila ANTES de la ventana; si el mercado no tiene ninguna (se sembró o
se operó por primera vez dentro de la ventana), se usa la primera fila de la
ventana. Sin LLM ni tablas nuevas.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.market import Market, MarketStatus
from app.models.price_history import PriceHistory

_ACTIVOS = (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION)
MAX_PUNTOS = 40      # puntos de la mini gráfica por mercado
CAMBIO_MINIMO = 1.0  # puntos porcentuales; por debajo no es "movimiento"


def _submuestrear(filas: list[PriceHistory]) -> list[PriceHistory]:
    """Paso uniforme, conservando siempre la primera y la última fila."""
    if len(filas) <= MAX_PUNTOS:
        return filas
    paso = (len(filas) - 1) / (MAX_PUNTOS - 1)
    idx = sorted({round(i * paso) for i in range(MAX_PUNTOS)} | {len(filas) - 1})
    return [filas[i] for i in idx]


async def calcular_movers(db: AsyncSession, horas: int, limite: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=horas)

    # 1) Filas dentro de la ventana, solo de mercados activos
    res = await db.execute(
        select(PriceHistory)
        .join(Market, Market.id == PriceHistory.market_id)
        .where(Market.status.in_(_ACTIVOS))
        .where(PriceHistory.recorded_at >= cutoff)
        .order_by(PriceHistory.market_id, PriceHistory.outcome_key, PriceHistory.recorded_at, PriceHistory.id)
    )
    ventana: dict[tuple[str, str | None], list[PriceHistory]] = defaultdict(list)
    for fila in res.scalars().all():
        ventana[(fila.market_id, fila.outcome_key)].append(fila)
    if not ventana:
        return []
    ids = sorted({mid for mid, _ in ventana})

    # 2) Línea base: última fila antes de la ventana por (mercado, outcome)
    ultima = (
        select(
            PriceHistory.market_id.label("mid"),
            PriceHistory.outcome_key.label("key"),
            func.max(PriceHistory.recorded_at).label("ts"),
        )
        .where(PriceHistory.market_id.in_(ids))
        .where(PriceHistory.recorded_at < cutoff)
        .group_by(PriceHistory.market_id, PriceHistory.outcome_key)
        .subquery()
    )
    res = await db.execute(
        select(PriceHistory).join(
            ultima,
            (PriceHistory.market_id == ultima.c.mid)
            & (PriceHistory.recorded_at == ultima.c.ts)
            & (func.coalesce(PriceHistory.outcome_key, "") == func.coalesce(ultima.c.key, "")),
        )
    )
    base: dict[tuple[str, str | None], PriceHistory] = {}
    for fila in res.scalars().all():
        base.setdefault((fila.market_id, fila.outcome_key), fila)

    res = await db.execute(select(Market).where(Market.id.in_(ids)).options(selectinload(Market.outcomes)))
    mercados = {m.id: m for m in res.scalars().all()}

    # 3) Cambio por (mercado, outcome); por mercado se queda el outcome que más se movió
    mejor: dict[str, dict] = {}
    for (mid, key), filas in ventana.items():
        m = mercados.get(mid)
        if m is None:
            continue
        es_multi = m.market_type == "multi"
        if (es_multi and key is None) or (not es_multi and key is not None):
            continue  # placeholder del seed / fila ajena al tipo
        antes = base.get((mid, key))
        serie = ([antes] if antes else []) + filas
        primero, ultimo = serie[0], serie[-1]
        cambio = ultimo.yes_price - primero.yes_price
        if abs(cambio) < CAMBIO_MINIMO:
            continue
        actual = mejor.get(mid)
        if actual and abs(actual["change"]) >= abs(cambio):
            continue
        etiqueta = None
        if es_multi:
            etiqueta = next((o.label for o in m.outcomes if o.outcome_key == key), key)
        mejor[mid] = {
            "id": m.id,
            "question": m.question,
            "category": m.category,
            "subcategory": m.subcategory,
            "image_url": m.image_url,
            "market_type": m.market_type,
            "status": m.status,
            "ends_at": m.ends_at,
            "outcome_key": key,
            "outcome_label": etiqueta,
            "price": ultimo.yes_price,
            "price_before": primero.yes_price,
            "change": cambio,
            "volume_delta": max(0.0, ultimo.volume_snapshot - primero.volume_snapshot),
            "points": [
                {"recorded_at": f.recorded_at, "price": f.yes_price} for f in _submuestrear(serie)
            ],
        }

    orden = sorted(mejor.values(), key=lambda d: (-abs(d["change"]), d["id"]))
    return orden[:limite]
