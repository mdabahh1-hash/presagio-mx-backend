from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import AsyncSessionLocal
from app.models.market import Market
from app.models.outcome import Outcome
from app.core.websocket_manager import ws_manager

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/market/{market_id}")
async def market_ws(market_id: str, ws: WebSocket):
    await ws_manager.connect_market(market_id, ws)
    try:
        # Snapshot uses a short-lived session so we don't pin a pooled DB
        # connection for the whole (potentially long) socket lifetime.
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Market).where(Market.id == market_id).options(selectinload(Market.outcomes))
            )
            market = result.scalar_one_or_none()
            snapshot: dict | None = None
            if market:
                snapshot = {
                    "market_id": market_id,
                    "yes_price": market.yes_price,
                    "no_price": round(100 - market.yes_price, 2),
                    "volume": market.volume,
                    "num_trades": market.num_trades,
                }
                if market.market_type == "multi" and market.outcomes:
                    snapshot["outcomes"] = [
                        {"outcome_key": o.outcome_key, "price": o.price}
                        for o in market.outcomes
                    ]
        if snapshot:
            await ws_manager.send_market_snapshot(market_id, ws, snapshot)
        # Keep connection alive, listening for client pings
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        # Runs on disconnect AND on any other error, so subscriptions never leak.
        ws_manager.disconnect_market(market_id, ws)


@router.websocket("/ws/feed")
async def feed_ws(ws: WebSocket):
    await ws_manager.connect_feed(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        ws_manager.disconnect_feed(ws)
