import asyncio
import logging
from typing import Dict, Set
from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages active WebSocket voice connections, connection limits, and interruption state.
    Enforces per-user connection limits and concurrency boundaries with automatic pruning.
    """

    MAX_CONNECTIONS_PER_USER: int = 5
    MAX_GLOBAL_CONNECTIONS: int = 500

    def __init__(self):
        # Map user_id to list of active WebSockets in chronological order
        self.active_connections: Dict[int, list[WebSocket]] = {}
        # Active cancellation events per connection
        self.interruption_events: Dict[WebSocket, asyncio.Event] = {}

    def _prune(self, user_id: int):
        """Prune any disconnected or closed sockets for this user."""
        if user_id in self.active_connections:
            alive = []
            for ws in self.active_connections[user_id]:
                if ws.client_state == WebSocketState.CONNECTED:
                    alive.append(ws)
                else:
                    if ws in self.interruption_events:
                        del self.interruption_events[ws]
            if alive:
                self.active_connections[user_id] = alive
            else:
                del self.active_connections[user_id]

    def can_connect(self, user_id: int) -> tuple[bool, str]:
        """Verify that global connection limits are not exceeded before accepting."""
        self._prune(user_id)
        total_active = sum(len(sockets) for sockets in self.active_connections.values())
        if total_active >= self.MAX_GLOBAL_CONNECTIONS:
            return False, "Server-wide WebSocket connection limit reached"
        return True, ""

    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept connection and manage user slot, gracefully closing oldest session if over limit."""
        await websocket.accept()
        self._prune(user_id)

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        # If user has reached max concurrent connections, close the oldest one cleanly
        while len(self.active_connections[user_id]) >= self.MAX_CONNECTIONS_PER_USER:
            oldest = self.active_connections[user_id].pop(0)
            if oldest in self.interruption_events:
                del self.interruption_events[oldest]
            try:
                if oldest.client_state == WebSocketState.CONNECTED:
                    await oldest.close(code=1000, reason="Replaced by new voice session")
            except Exception:
                pass

        self.active_connections[user_id].append(websocket)
        self.interruption_events[websocket] = asyncio.Event()
        logger.info(f"WebSocket client connected: user {user_id} (active: {len(self.active_connections[user_id])})")

    def disconnect(self, websocket: WebSocket, user_id: int):
        """Cleanly remove a websocket from tracking."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        if websocket in self.interruption_events:
            del self.interruption_events[websocket]
        logger.info(f"WebSocket client disconnected: user {user_id}")

    def trigger_interrupt(self, websocket: WebSocket):
        """Signal ongoing audio generation for this socket to abort immediately."""
        if websocket in self.interruption_events:
            self.interruption_events[websocket].set()
            logger.info("Interruption triggered for active voice stream.")

    def reset_interrupt(self, websocket: WebSocket):
        """Reset the interruption event for a new conversation turn."""
        if websocket in self.interruption_events:
            self.interruption_events[websocket].clear()

    def is_interrupted(self, websocket: WebSocket) -> bool:
        """Check if interruption was flagged."""
        if websocket in self.interruption_events:
            return self.interruption_events[websocket].is_set()
        return False

manager = ConnectionManager()
