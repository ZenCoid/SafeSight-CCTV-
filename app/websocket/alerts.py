"""
SafeSight CCTV - WebSocket Alert Manager

Real-time push notifications for violation events.
Frontend connects via /ws/alerts and receives instant updates.

Preserved exactly from original main.py — no changes needed,
just moved to its own module for cleaner architecture.
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for real-time alert broadcasting."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        logger.debug("WebSocket client connected (total: {})", len(self.connections))

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            logger.debug("WebSocket client disconnected (total: {})", len(self.connections))

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected WebSocket clients."""
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_sync(self, message: dict):
        """Non-async broadcast from sync code (schedules on event loop).

        Used by the detector's violation callback which runs in the
        stream generator thread, not the async event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.broadcast(message))
        except RuntimeError:
            pass


ws_manager = ConnectionManager()


@router.websocket("/ws/alerts")
async def websocket_alerts(ws: WebSocket):
    """WebSocket endpoint for real-time violation alerts.

    Frontend can connect and send "ping" to keep alive.
    Violation events are broadcast as JSON:
    {"type": "violation", "camera_id": "...", "detection_type": "...", "confidence": ...}
    """
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)