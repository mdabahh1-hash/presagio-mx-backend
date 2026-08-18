"""Admin endpoints to seed markets and resolve them."""
import asyncio
from app.core.background import spawn
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.position import Position
from app.models.user import User
from app.schemas.market import MarketResolve
from app.core.auth import get_current_user, require_admin as _require_admin
from app.core import lmsr
from app.services.email import send_resolution_email
from app.services import ledger

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/markets/{market_id}/resolve")
async def resolve_market(
    market_id: str,
    payload: MarketResolve,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail={"code": "MARKET_NOT_FOUND", "message": "Mercado no encontrado"})
    if market.status not in (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION, MarketStatus.CLOSED):
        raise HTTPException(status_code=400, detail={"code": "MARKET_ALREADY_RESOLVED", "message": "Mercado ya resuelto o cancelado"})

    positions_result = await db.execute(
        select(Position).where(Position.market_id == market_id, Position.shares > 0)
    )
    positions = positions_result.scalars().all()
    notify: dict[int, dict] = {}

    if market.market_type == "multi":
        # ── Multi-outcome resolution ─────────────────────────────────────────
        if not payload.outcome_key:
            raise HTTPException(status_code=400, detail={"code": "OUTCOME_KEY_REQUIRED", "message": "Especifica 'outcome_key' para mercados multi-resultado"})

        outcomes_res = await db.execute(
            select(Outcome).where(Outcome.market_id == market_id)
        )
        valid_keys = {o.outcome_key for o in outcomes_res.scalars().all()}
        if payload.outcome_key not in valid_keys:
            raise HTTPException(status_code=400, detail={"code": "INVALID_OUTCOME_KEY", "message": f"outcome_key inválido: {payload.outcome_key}"})

        market.status = MarketStatus.RESOLVED
        market.resolved_outcome_key = payload.outcome_key
        market.resolved_at = datetime.now(timezone.utc)

        for pos in positions:
            user_result = await db.execute(
                select(User).where(User.id == pos.user_id).with_for_update()
            )
            user = user_result.scalar_one_or_none()
            if not user:
                continue

            payout = pos.shares if pos.outcome_key == payload.outcome_key else 0.0
            user.points += payout
            ledger.record(db, user.id, payout, "payout")
            user.total_predictions += 1
            if pos.outcome_key == payload.outcome_key:
                user.correct_predictions += 1
            pos.shares = 0

            if user.email and user.email_notifications:
                entry = notify.setdefault(
                    user.id,
                    {"email": user.email, "name": user.display_name, "payout": 0.0},
                )
                entry["payout"] += payout

        await db.commit()

        question = market.question
        for entry in notify.values():
            won = entry["payout"] > 0
            spawn(
                send_resolution_email(entry["email"], entry["name"], question, won, entry["payout"])
            )

        return {
            "ok": True,
            "resolution": payload.outcome_key,
            "positions_settled": len(positions),
        }

    else:
        # ── Binary resolution (unchanged) ────────────────────────────────────
        if not payload.resolution:
            raise HTTPException(status_code=400, detail={"code": "RESOLUTION_REQUIRED", "message": "Especifica 'resolution' (YES o NO) para mercados binarios"})

        resolution = payload.resolution.upper()
        if resolution not in ("YES", "NO"):
            raise HTTPException(status_code=400, detail={"code": "INVALID_RESOLUTION", "message": "Resolución debe ser YES o NO"})

        market.status = MarketStatus.RESOLVED_YES if resolution == "YES" else MarketStatus.RESOLVED_NO
        market.resolved_at = datetime.now(timezone.utc)

        for pos in positions:
            user_result = await db.execute(
                select(User).where(User.id == pos.user_id).with_for_update()
            )
            user = user_result.scalar_one_or_none()
            if not user:
                continue

            side_val = pos.outcome_key or (pos.side.value if pos.side else "")
            payout = (
                lmsr.payout_if_yes(side_val, pos.shares)
                if resolution == "YES"
                else lmsr.payout_if_no(side_val, pos.shares)
            )
            user.points += payout
            ledger.record(db, user.id, payout, "payout")
            user.total_predictions += 1
            if (resolution == "YES" and side_val == "YES") or (resolution == "NO" and side_val == "NO"):
                user.correct_predictions += 1
            pos.shares = 0

            if user.email and user.email_notifications:
                entry = notify.setdefault(
                    user.id,
                    {"email": user.email, "name": user.display_name, "payout": 0.0},
                )
                entry["payout"] += payout

        await db.commit()

        question = market.question
        for entry in notify.values():
            won = entry["payout"] > 0
            spawn(
                send_resolution_email(entry["email"], entry["name"], question, won, entry["payout"])
            )

        return {"ok": True, "resolution": resolution, "positions_settled": len(positions)}


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
