"""WebSocket real-time manager for broadcasting project events."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class RealtimeManager:
    def __init__(self) -> None:
        self._project_connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._project_connections[project_id].add(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        connections = self._project_connections.get(project_id, set())
        connections.discard(websocket)
        if not connections:
            self._project_connections.pop(project_id, None)

    async def broadcast(self, project_id: str, event: str, payload: Any = None) -> None:
        connections = list(self._project_connections.get(project_id, set()))
        if not connections:
            return
        message = {
            "event": event,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(project_id, ws)
