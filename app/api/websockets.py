from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.market import Market
from app.core.websocket_manager import ws_manager

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/market/{market_id}")
async def market_ws(market_id: str, ws: WebSocket, db: AsyncSession = Depends(get_db)):
    await ws_manager.connect_market(market_id, ws)
    try:
        # Send current snapshot on connect
        result = await db.execute(select(Market).where(Market.id == market_id))
        market = result.scalar_one_or_none()
        if market:
            await ws_manager.send_market_snapshot(market_id, ws, {
                "market_id": market_id,
                "yes_price": market.yes_price,
                "no_price": round(100 - market.yes_price, 2),
                "volume": market.volume,
                "num_trades": market.num_trades,
            })
        # Keep connection alive, listening for client pings
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
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
