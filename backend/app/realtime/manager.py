import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class RealtimeManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, house_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[house_id].add(websocket)

    async def disconnect(self, house_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[house_id].discard(websocket)
            if not self._connections[house_id]:
                self._connections.pop(house_id, None)

    async def broadcast(self, house_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._connections.get(house_id, set()))
        dead: list[WebSocket] = []
        for websocket in clients:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            await self.disconnect(house_id, websocket)

    @property
    def connection_count(self) -> int:
        return sum(len(items) for items in self._connections.values())


realtime_manager = RealtimeManager()
