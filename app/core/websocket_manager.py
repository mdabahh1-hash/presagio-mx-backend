import asyncio
import json
from typing import DefaultDict
from collections import defaultdict
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # market_id -> set of websockets subscribed to that market
        self._market_subs: DefaultDict[str, set[WebSocket]] = defaultdict(set)
        # global activity feed subscribers
        self._feed_subs: set[WebSocket] = set()

    async def connect_market(self, market_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._market_subs[market_id].add(ws)

    def disconnect_market(self, market_id: str, ws: WebSocket) -> None:
        self._market_subs[market_id].discard(ws)

    async def connect_feed(self, ws: WebSocket) -> None:
        await ws.accept()
        self._feed_subs.add(ws)

    def disconnect_feed(self, ws: WebSocket) -> None:
        self._feed_subs.discard(ws)

    async def broadcast_market_update(self, market_id: str, payload: dict) -> None:
        """Send price update to all subscribers of a specific market."""
        dead: set[WebSocket] = set()
        msg = json.dumps({"type": "price_update", **payload})
        for ws in list(self._market_subs[market_id]):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._market_subs[market_id].discard(ws)

    async def broadcast_feed(self, payload: dict) -> None:
        """Send activity event to all global feed subscribers."""
        dead: set[WebSocket] = set()
        msg = json.dumps({"type": "activity", **payload})
        for ws in list(self._feed_subs):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._feed_subs.discard(ws)

    async def send_market_snapshot(self, market_id: str, ws: WebSocket, snapshot: dict) -> None:
        """Send current state to newly connected client."""
        try:
            await ws.send_text(json.dumps({"type": "snapshot", **snapshot}))
        except Exception as e:
            logger.warning(f"Failed to send snapshot: {e}")


ws_manager = ConnectionManager()
