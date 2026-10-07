import asyncio
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jwt import InvalidTokenError
from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import SessionFactory
from app.models.domain import House, User
from app.realtime.manager import realtime_manager

router = APIRouter()
settings = get_settings()


async def authenticate_socket(websocket: WebSocket) -> User | None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return None
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        if payload.get("type") != "access" or not user_id:
            raise InvalidTokenError("Invalid token type")
    except InvalidTokenError:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return None
    async with SessionFactory() as db:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4403, reason="Account unavailable")
            return None
        return user


@router.websocket("/ws/houses/{house_id}")
async def house_updates(websocket: WebSocket, house_id: str) -> None:
    user = await authenticate_socket(websocket)
    if user is None:
        return
    if user.house_id != house_id and user.role.name not in {"admin", "owner"}:
        await websocket.close(code=4403, reason="House access denied")
        return
    await realtime_manager.connect(house_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "house_id": house_id})
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await realtime_manager.disconnect(house_id, websocket)


@router.websocket("/ws/live-stream")
async def live_stream(websocket: WebSocket) -> None:
    """Multiplexed delta stream from the authoritative API contract."""
    user = await authenticate_socket(websocket)
    if user is None:
        return
    async with SessionFactory() as db:
        house_id = user.house_id
        if house_id is None and user.role.name in {"admin", "owner"}:
            house_id = await db.scalar(select(House.id).order_by(House.created_at).limit(1))
    if house_id is None:
        await websocket.close(code=4404, reason="No house assigned")
        return
    await realtime_manager.connect(house_id, websocket)
    try:
        await websocket.send_json(
            {"event": "CONNECTED", "timestamp": int(datetime.now(UTC).timestamp() * 1000)}
        )
        while True:
            try:
                frame = await asyncio.wait_for(websocket.receive_json(), timeout=15)
            except TimeoutError:
                await websocket.send_json(
                    {"type": "PING", "ts": int(datetime.now(UTC).timestamp() * 1000)}
                )
                try:
                    frame = await asyncio.wait_for(websocket.receive_json(), timeout=5)
                except TimeoutError:
                    await websocket.close(code=4408, reason="Heartbeat timeout")
                    break
            if frame.get("type") == "PONG":
                continue
            if frame.get("action") == "SUBSCRIBE":
                channels = [str(item) for item in frame.get("channels", [])[:50]]
                await websocket.send_json({"event": "SUBSCRIBED", "channels": channels})
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_manager.disconnect(house_id, websocket)
