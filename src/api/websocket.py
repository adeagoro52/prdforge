"""WebSocket endpoints for real-time updates."""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

websocket_router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        # Map of run_id to set of connected WebSockets
        self.run_connections: Dict[str, Set[WebSocket]] = {}
        # All active connections (for broadcast)
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, run_id: str | None = None):
        """Accept a WebSocket connection.

        Args:
            websocket: The WebSocket to connect.
            run_id: Optional run ID to subscribe to.
        """
        await websocket.accept()
        self.active_connections.add(websocket)

        if run_id:
            if run_id not in self.run_connections:
                self.run_connections[run_id] = set()
            self.run_connections[run_id].add(websocket)

    def disconnect(self, websocket: WebSocket, run_id: str | None = None):
        """Disconnect a WebSocket.

        Args:
            websocket: The WebSocket to disconnect.
            run_id: Optional run ID to unsubscribe from.
        """
        self.active_connections.discard(websocket)

        if run_id and run_id in self.run_connections:
            self.run_connections[run_id].discard(websocket)
            if not self.run_connections[run_id]:
                del self.run_connections[run_id]

    async def broadcast_to_run(self, run_id: str, message: dict):
        """Broadcast a message to all connections for a run.

        Args:
            run_id: The run ID to broadcast to.
            message: The message to send.
        """
        if run_id not in self.run_connections:
            return

        dead_connections = set()
        for connection in self.run_connections[run_id]:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn, run_id)

    async def broadcast_all(self, message: dict):
        """Broadcast a message to all connected clients.

        Args:
            message: The message to send.
        """
        dead_connections = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections.discard(conn)


# Global connection manager
manager = ConnectionManager()


@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """General WebSocket endpoint for dashboard updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle subscription messages
            if message.get("type") == "subscribe":
                run_id = message.get("run_id")
                if run_id:
                    if run_id not in manager.run_connections:
                        manager.run_connections[run_id] = set()
                    manager.run_connections[run_id].add(websocket)
                    await websocket.send_json({
                        "type": "subscribed",
                        "run_id": run_id,
                    })

            elif message.get("type") == "unsubscribe":
                run_id = message.get("run_id")
                if run_id and run_id in manager.run_connections:
                    manager.run_connections[run_id].discard(websocket)

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@websocket_router.websocket("/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for a specific run's updates."""
    await manager.connect(websocket, run_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, run_id)


# Helper functions for broadcasting events
async def broadcast_run_update(run_id: str, status: str, progress: dict):
    """Broadcast a run status update.

    Args:
        run_id: The run ID.
        status: New status.
        progress: Progress data (completed_tasks, failed_tasks, etc.).
    """
    await manager.broadcast_to_run(run_id, {
        "type": "run_update",
        "run_id": run_id,
        "status": status,
        "progress": progress,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_task_update(
    run_id: str,
    task_id: str,
    status: str,
    output: str | None = None,
):
    """Broadcast a task status update.

    Args:
        run_id: The run ID.
        task_id: The task ID.
        status: New task status.
        output: Optional task output.
    """
    await manager.broadcast_to_run(run_id, {
        "type": "task_update",
        "run_id": run_id,
        "task_id": task_id,
        "status": status,
        "output": output,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_log_entry(
    run_id: str,
    level: str,
    message: str,
    task_id: str | None = None,
):
    """Broadcast a log entry.

    Args:
        run_id: The run ID.
        level: Log level (info, warning, error).
        message: Log message.
        task_id: Optional task ID.
    """
    await manager.broadcast_to_run(run_id, {
        "type": "log",
        "run_id": run_id,
        "task_id": task_id,
        "level": level,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    })
