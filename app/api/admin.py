"""Admin endpoints to seed markets and resolve them."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market, MarketStatus
from app.models.position import Position
from app.models.user import User
from app.schemas.market import MarketResolve
from app.core.auth import get_current_user
from app.core import lmsr

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/markets/{market_id}/resolve")
async def resolve_market(
    market_id: str,
    payload: MarketResolve,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Mercado no encontrado")
    if market.status != MarketStatus.OPEN:
        raise HTTPException(status_code=400, detail="Mercado ya resuelto o cancelado")

    resolution = payload.resolution.upper()
    if resolution not in ("YES", "NO"):
        raise HTTPException(status_code=400, detail="Resolución debe ser YES o NO")

    market.status = MarketStatus.RESOLVED_YES if resolution == "YES" else MarketStatus.RESOLVED_NO
    market.resolved_at = datetime.now(timezone.utc)

    # Pay out all positions
    positions_result = await db.execute(
        select(Position).where(Position.market_id == market_id, Position.shares > 0)
    )
    positions = positions_result.scalars().all()

    for pos in positions:
        user_result = await db.execute(
            select(User).where(User.id == pos.user_id).with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        payout = (
            lmsr.payout_if_yes(pos.side.value, pos.shares)
            if resolution == "YES"
            else lmsr.payout_if_no(pos.side.value, pos.shares)
        )
        user.points += payout
        user.total_predictions += 1
        if (resolution == "YES" and pos.side.value == "YES") or (resolution == "NO" and pos.side.value == "NO"):
            user.correct_predictions += 1
        pos.shares = 0  # Mark as settled

    await db.commit()
    return {"ok": True, "resolution": resolution, "positions_settled": len(positions)}


@router.post("/markets/{market_id}/toggle-trending")
async def toggle_trending(
    market_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Mercado no encontrado")
    market.trending = not market.trending
    await db.commit()
    return {"ok": True, "trending": market.trending}
