"""Admin endpoints to resolve markets and toggle trending.

La liquidación vive en app/services/resolution.py (compartida con el plan
nocturno); aquí solo se autentica y se traducen los errores de dominio a HTTP.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.user import User
from app.schemas.market import MarketPatch, MarketResolve
from app.core.auth import get_current_user, require_admin as _require_admin
from app.services import resolution

router = APIRouter(prefix="/admin", tags=["admin"])

_EDITABLES = (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION, MarketStatus.CLOSED)


@router.post("/markets/{market_id}/cancel")
async def cancel_market(
    market_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancela un mercado y reembolsa `shares * avg_cost` a cada posición
    (ledger "refund"); anula los picks de ligas. Irreversible."""
    _require_admin(current_user)
    try:
        return await resolution.cancel(db, market_id)
    except resolution.ResolutionError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})


@router.patch("/markets/{market_id}")
async def patch_market(
    market_id: str,
    payload: MarketPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edita un mercado NO resuelto: reabrirlo (`status: open` + `ends_at`
    futuro, p. ej. un partido aplazado con nueva fecha), cambiar pregunta,
    normas, contexto o etiquetas de outcomes. Nunca toca precios ni posiciones."""
    _require_admin(current_user)
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail={"code": "MARKET_NOT_FOUND", "message": "Mercado no encontrado"})
    if market.status not in _EDITABLES:
        raise HTTPException(status_code=400, detail={"code": "MARKET_ALREADY_RESOLVED", "message": "Mercado ya resuelto o cancelado"})

    cambios: list[str] = []
    if payload.ends_at is not None:
        ends_at = payload.ends_at if payload.ends_at.tzinfo else payload.ends_at.replace(tzinfo=timezone.utc)
        market.ends_at = ends_at
        cambios.append("ends_at")
    if payload.status == "open":
        if market.ends_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail={"code": "ENDS_AT_IN_PAST", "message": "Para reabrir, ends_at debe estar en el futuro"})
        market.status = MarketStatus.OPEN
        # que los avisos de cierre / recordatorio de resolución vuelvan a dispararse
        for attr in ("closing_notified_at", "resolution_reminded_at"):
            if hasattr(market, attr):
                setattr(market, attr, None)
        cambios.append("status")
    for campo in ("question", "rules", "context"):
        valor = getattr(payload, campo)
        if valor is not None:
            setattr(market, campo, valor)
            cambios.append(campo)
    if payload.auto_resolucion is not None:
        from app.services.resolucion.recetas import validar_receta

        if payload.auto_resolucion == {}:
            market.auto_resolucion = None
        else:
            errs = validar_receta(payload.auto_resolucion, market.market_type)
            if errs:
                raise HTTPException(status_code=422, detail={"code": "RECETA_INVALIDA", "message": "; ".join(errs)})
            market.auto_resolucion = payload.auto_resolucion
        cambios.append("auto_resolucion")
    if payload.outcome_labels:
        res = await db.execute(select(Outcome).where(Outcome.market_id == market_id))
        por_key = {o.outcome_key: o for o in res.scalars().all()}
        desconocidas = sorted(set(payload.outcome_labels) - set(por_key))
        if desconocidas:
            raise HTTPException(status_code=400, detail={"code": "INVALID_OUTCOME_KEY", "message": f"outcome_key inválido: {', '.join(desconocidas)}"})
        for key, label in payload.outcome_labels.items():
            por_key[key].label = label
        cambios.append("outcome_labels")
    await db.commit()
    return {"ok": True, "id": market.id, "status": market.status.value, "ends_at": market.ends_at.isoformat(), "cambios": cambios}


@router.post("/markets/{market_id}/resolve")
async def resolve_market(
    market_id: str,
    payload: MarketResolve,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    try:
        return await resolution.resolve(
            db, market_id, resolution=payload.resolution, outcome_key=payload.outcome_key
        )
    except resolution.ResolutionError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})


@router.post("/markets/{market_id}/toggle-trending")
async def toggle_trending(
    market_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail={"code": "MARKET_NOT_FOUND", "message": "Mercado no encontrado"})
    market.trending = not market.trending
    await db.commit()
    return {"ok": True, "trending": market.trending}
