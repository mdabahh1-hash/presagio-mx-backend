from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market, MarketStatus
from app.models.trade import Trade
from app.models.position import Position
from app.models.price_history import PriceHistory
from app.models.user import User
from app.schemas.trade import TradeRequest, TradeResponse, PositionOut
from app.core.auth import get_current_user
from app.core import lmsr
from app.core.websocket_manager import ws_manager

router = APIRouter(prefix="/markets", tags=["trades"])


@router.post("/{market_id}/trade", response_model=TradeResponse)
async def execute_trade(
    market_id: str,
    payload: TradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Load market with row-level lock to prevent race conditions
    result = await db.execute(
        select(Market).where(Market.id == market_id).with_for_update()
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Mercado no encontrado")
    if market.status != MarketStatus.OPEN:
        raise HTTPException(status_code=400, detail="Este mercado ya no acepta operaciones")

    if current_user.points < payload.points:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente. Tienes {current_user.points:.0f} PT, necesitas {payload.points:.0f} PT",
        )

    # Compute how many shares the user gets for `payload.points`
    buy_yes = payload.side.value == "YES"
    price_before = market.yes_price

    shares = lmsr.shares_for_cost(
        market.q_yes, market.q_no, market.b, payload.points, buy_yes
    )

    # Verify cost (should equal payload.points within tolerance)
    if buy_yes:
        actual_cost = lmsr.trade_cost(market.q_yes, market.q_no, market.b, shares, 0.0)
        market.q_yes += shares
    else:
        actual_cost = lmsr.trade_cost(market.q_yes, market.q_no, market.b, 0.0, shares)
        market.q_no += shares

    # Update market state
    market.yes_price = lmsr.yes_price_pct(market.q_yes, market.q_no, market.b)
    market.volume += actual_cost
    market.num_trades += 1

    price_after = market.yes_price

    # Deduct points from user
    current_user.points -= actual_cost
    current_user.markets_traded += 1

    # Record trade
    trade = Trade(
        user_id=current_user.id,
        market_id=market_id,
        side=payload.side,
        shares=shares,
        cost=actual_cost,
        price_before=price_before,
        price_after=price_after,
    )
    db.add(trade)

    # Upsert position
    pos_result = await db.execute(
        select(Position).where(
            Position.user_id == current_user.id,
            Position.market_id == market_id,
            Position.side == payload.side,
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
            shares=shares,
            avg_cost=actual_cost / shares,
        )
        db.add(position)

    # Record price history point
    ph = PriceHistory(
        market_id=market_id,
        yes_price=market.yes_price,
        volume_snapshot=market.volume,
    )
    db.add(ph)

    await db.commit()
    await db.refresh(trade)

    # Broadcast WebSocket update (fire and forget)
    import asyncio
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
        shares=shares,
        cost=actual_cost,
        price_before=price_before,
        price_after=price_after,
        created_at=trade.created_at,
        new_yes_price=market.yes_price,
        new_balance=current_user.points,
    )


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
