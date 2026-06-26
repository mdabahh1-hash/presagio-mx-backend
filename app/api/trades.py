from datetime import datetime, timezone
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.trade import Trade
from app.models.position import Position
from app.models.price_history import PriceHistory
from app.models.user import User
from app.schemas.trade import TradeRequest, TradeResponse, PositionOut
from app.schemas.market import OutcomeOut
from app.core.auth import get_current_user
from app.core import lmsr
from app.core.websocket_manager import ws_manager
from app.services import ledger, referral

router = APIRouter(prefix="/markets", tags=["trades"])


@router.post("/{market_id}/trade", response_model=TradeResponse)
async def execute_trade(
    market_id: str,
    payload: TradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Market).where(Market.id == market_id).with_for_update()
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Mercado no encontrado")
    if market.status != MarketStatus.OPEN:
        raise HTTPException(status_code=400, detail="Este mercado ya no acepta operaciones")
    if market.ends_at < datetime.now(timezone.utc):
        market.status = MarketStatus.PENDING_RESOLUTION
        await db.commit()
        raise HTTPException(status_code=400, detail="Este mercado cerró y está pendiente de resolución")

    if current_user.points < payload.points:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente. Tienes {current_user.points:.0f} PT, necesitas {payload.points:.0f} PT",
        )

    if market.market_type == "multi":
        # ── Multi-outcome LMSR path ──────────────────────────────────────────
        if not payload.outcome_key:
            raise HTTPException(status_code=400, detail="Este es un mercado multi-resultado; debes especificar 'outcome_key'")

        outcomes_res = await db.execute(
            select(Outcome).where(Outcome.market_id == market_id).with_for_update()
        )
        outcomes: list[Outcome] = list(outcomes_res.scalars().all())
        if not outcomes:
            raise HTTPException(status_code=500, detail="Mercado mal configurado: sin resultados")

        target_outcome = next((o for o in outcomes if o.outcome_key == payload.outcome_key), None)
        if not target_outcome:
            raise HTTPException(status_code=400, detail=f"Resultado desconocido: {payload.outcome_key}")

        q_dict = {o.outcome_key: o.q for o in outcomes}
        price_before = target_outcome.price

        shares = lmsr.shares_for_cost_multi(q_dict, market.b, payload.outcome_key, payload.points)
        actual_cost = lmsr.trade_cost_multi(q_dict, market.b, payload.outcome_key, shares)

        # Update LMSR state
        target_outcome.q += shares
        q_dict[payload.outcome_key] = target_outcome.q

        # Recompute all outcome prices
        new_prices = lmsr.prices_multi(q_dict, market.b)
        for o in outcomes:
            o.price = new_prices[o.outcome_key]

        price_after = target_outcome.price
        market.volume += actual_cost
        market.num_trades += 1
        current_user.points -= actual_cost
        ledger.record(db, current_user.id, -actual_cost, "trade")
        if current_user.markets_traded == 0:
            await referral.credit_referral(db, current_user)
        current_user.markets_traded += 1

        trade = Trade(
            user_id=current_user.id,
            market_id=market_id,
            side=None,
            outcome_key=payload.outcome_key,
            shares=shares,
            cost=actual_cost,
            price_before=price_before,
            price_after=price_after,
        )
        db.add(trade)

        pos_result = await db.execute(
            select(Position).where(
                Position.user_id == current_user.id,
                Position.market_id == market_id,
                Position.outcome_key == payload.outcome_key,
            ).with_for_update()
        )
        position = pos_result.scalar_one_or_none()
        if position:
            total_cost = position.avg_cost * position.shares + actual_cost
            position.shares += shares
            position.avg_cost = total_cost / position.shares
        else:
            position = Position(
                user_id=current_user.id,
                market_id=market_id,
                side=None,
                outcome_key=payload.outcome_key,
                shares=shares,
                avg_cost=actual_cost / shares,
            )
            db.add(position)

        for o in outcomes:
            db.add(PriceHistory(
                market_id=market_id,
                outcome_key=o.outcome_key,
                yes_price=o.price,
                volume_snapshot=market.volume,
            ))

        await db.commit()
        await db.refresh(trade)

        asyncio.create_task(ws_manager.broadcast_market_update(market_id, {
            "market_id": market_id,
            "yes_price": target_outcome.price,
            "volume": market.volume,
            "num_trades": market.num_trades,
            "outcomes": [{"outcome_key": o.outcome_key, "price": o.price} for o in outcomes],
            "trade": {
                "outcome_key": payload.outcome_key,
                "label": target_outcome.label,
                "shares": round(shares, 4),
                "cost": round(actual_cost, 2),
                "user": current_user.display_name,
            },
        }))
        asyncio.create_task(ws_manager.broadcast_feed({
            "market_id": market_id,
            "question": market.question[:80],
            "outcome_key": payload.outcome_key,
            "yes_price": target_outcome.price,
            "user": current_user.display_name,
        }))

        return TradeResponse(
            id=trade.id,
            market_id=market_id,
            side=None,
            outcome_key=payload.outcome_key,
            shares=shares,
            cost=actual_cost,
            price_before=price_before,
            price_after=price_after,
            created_at=trade.created_at,
            new_yes_price=target_outcome.price,
            new_balance=current_user.points,
        )

    else:
        # ── Binary LMSR path (unchanged) ─────────────────────────────────────
        if not payload.side:
            raise HTTPException(status_code=400, detail="Este es un mercado binario; debes especificar 'side'")

        buy_yes = payload.side.value == "YES"
        price_before = market.yes_price

        shares = lmsr.shares_for_cost(
            market.q_yes, market.q_no, market.b, payload.points, buy_yes
        )

        if buy_yes:
            actual_cost = lmsr.trade_cost(market.q_yes, market.q_no, market.b, shares, 0.0)
            market.q_yes += shares
        else:
            actual_cost = lmsr.trade_cost(market.q_yes, market.q_no, market.b, 0.0, shares)
            market.q_no += shares

        market.yes_price = lmsr.yes_price_pct(market.q_yes, market.q_no, market.b)
        market.volume += actual_cost
        market.num_trades += 1

        price_after = market.yes_price
        current_user.points -= actual_cost
        ledger.record(db, current_user.id, -actual_cost, "trade")
        if current_user.markets_traded == 0:
            await referral.credit_referral(db, current_user)
        current_user.markets_traded += 1

        trade = Trade(
            user_id=current_user.id,
            market_id=market_id,
            side=payload.side,
            outcome_key=payload.side.value,
            shares=shares,
            cost=actual_cost,
            price_before=price_before,
            price_after=price_after,
        )
        db.add(trade)

        pos_result = await db.execute(
            select(Position).where(
                Position.user_id == current_user.id,
                Position.market_id == market_id,
                Position.outcome_key == payload.side.value,
            ).with_for_update()
        )
        position = pos_result.scalar_one_or_none()
        if position:
            total_cost = position.avg_cost * position.shares + actual_cost
            position.shares += shares
            position.avg_cost = total_cost / position.shares
        else:
            position = Position(
                user_id=current_user.id,
                market_id=market_id,
                side=payload.side,
                outcome_key=payload.side.value,
                shares=shares,
                avg_cost=actual_cost / shares,
            )
            db.add(position)

        ph = PriceHistory(
            market_id=market_id,
            yes_price=market.yes_price,
            volume_snapshot=market.volume,
        )
        db.add(ph)

        await db.commit()
        await db.refresh(trade)

        asyncio.create_task(ws_manager.broadcast_market_update(market_id, {
            "market_id": market_id,
            "yes_price": market.yes_price,
            "no_price": round(100 - market.yes_price, 2),
            "volume": market.volume,
            "num_trades": market.num_trades,
            "trade": {
                "side": payload.side.value,
                "shares": round(shares, 4),
                "cost": round(actual_cost, 2),
                "user": current_user.display_name,
            },
        }))
        asyncio.create_task(ws_manager.broadcast_feed({
            "market_id": market_id,
            "question": market.question[:80],
            "side": payload.side.value,
            "yes_price": market.yes_price,
            "user": current_user.display_name,
        }))

        return TradeResponse(
            id=trade.id,
            market_id=market_id,
            side=payload.side,
            outcome_key=payload.side.value,
            shares=shares,
            cost=actual_cost,
            price_before=price_before,
            price_after=price_after,
            created_at=trade.created_at,
            new_yes_price=market.yes_price,
            new_balance=current_user.points,
        )


@router.get("/{market_id}/outcomes", response_model=list[OutcomeOut])
async def get_market_outcomes(market_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Outcome)
        .where(Outcome.market_id == market_id)
        .order_by(Outcome.price.desc())
    )
    return result.scalars().all()


@router.get("/{market_id}/positions", response_model=list[PositionOut])
async def get_market_positions(
    market_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Position).where(
            Position.user_id == current_user.id,
            Position.market_id == market_id,
        )
    )
    return result.scalars().all()
