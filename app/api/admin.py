"""Admin endpoints to resolve markets and toggle trending.

La liquidación vive en app/services/resolution.py (compartida con el plan
nocturno); aquí solo se autentica y se traducen los errores de dominio a HTTP.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market
from app.models.user import User
from app.schemas.market import MarketResolve
from app.core.auth import get_current_user, require_admin as _require_admin
from app.services import resolution

router = APIRouter(prefix="/admin", tags=["admin"])


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
