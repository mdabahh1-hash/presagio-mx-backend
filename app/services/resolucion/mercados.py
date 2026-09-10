"""Mercados pendientes leídos de la BD en el mismo formato que devuelve el API
pública (`agent-resolver.py list`), para que `armar_plan` y `validar_entrada`
sirvan igual desde el CLI y desde el servidor."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome


def mercado_a_dict(m: Market, outcomes: list[Outcome]) -> dict:
    return {
        "id": m.id,
        "question": m.question,
        "market_type": m.market_type,
        "category": m.category.value if hasattr(m.category, "value") else str(m.category),
        "subcategory": m.subcategory,
        "kind": m.kind,
        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
        "ends_at": m.ends_at.isoformat().replace("+00:00", "Z") if m.ends_at else None,
        "volume": m.volume,
        "num_trades": m.num_trades,
        "yes_price": m.yes_price,
        "resolution_criteria": m.resolution_criteria,
        "resolution_source_url": getattr(m, "resolution_source_url", None),
        "rules": getattr(m, "rules", None),
        "outcomes": [
            {"outcome_key": o.outcome_key, "label": o.label, "price": o.price} for o in outcomes
        ],
    }


async def _outcomes_por_mercado(db: AsyncSession, ids: list[str]) -> dict[str, list[Outcome]]:
    if not ids:
        return {}
    res = await db.execute(select(Outcome).where(Outcome.market_id.in_(ids)).order_by(Outcome.id))
    por: dict[str, list[Outcome]] = {i: [] for i in ids}
    for o in res.scalars().all():
        por.setdefault(o.market_id, []).append(o)
    return por


async def pendientes_como_dicts(db: AsyncSession) -> list[dict]:
    res = await db.execute(
        select(Market).where(Market.status == MarketStatus.PENDING_RESOLUTION).order_by(Market.ends_at)
    )
    mercados = res.scalars().all()
    outcomes = await _outcomes_por_mercado(db, [m.id for m in mercados])
    return [mercado_a_dict(m, outcomes.get(m.id, [])) for m in mercados]


async def detalle_actual(db: AsyncSession, market_id: str) -> dict | None:
    """Estado fresco de un mercado (para re-validar justo antes de aplicar)."""
    m = (await db.execute(select(Market).where(Market.id == market_id))).scalar_one_or_none()
    if m is None:
        return None
    outcomes = await _outcomes_por_mercado(db, [m.id])
    return mercado_a_dict(m, outcomes.get(m.id, []))
