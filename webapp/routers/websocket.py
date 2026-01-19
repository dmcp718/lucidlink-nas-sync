"""
WebSocket handlers for real-time updates.
"""
import asyncio
import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from webapp.models.sync_job import SyncProgress
from webapp.services.sync_manager import sync_manager
from webapp.services.log_streamer import log_streamer

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for broadcasting."""

    def __init__(self):
        # Connections organized by channel type
        self.progress_connections: dict[str, Set[WebSocket]] = {}  # job_id -> connections
        self.log_connections: Set[WebSocket] = set()

    async def connect_progress(self, websocket: WebSocket, job_id: str):
        """Connect a client to progress updates for a job."""
        await websocket.accept()
        if job_id not in self.progress_connections:
            self.progress_connections[job_id] = set()
        self.progress_connections[job_id].add(websocket)

    def disconnect_progress(self, websocket: WebSocket, job_id: str):
        """Disconnect a client from progress updates."""
        if job_id in self.progress_connections:
            self.progress_connections[job_id].discard(websocket)
            if not self.progress_connections[job_id]:
                del self.progress_connections[job_id]

    async def connect_logs(self, websocket: WebSocket):
        """Connect a client to log streaming."""
        await websocket.accept()
        self.log_connections.add(websocket)

    def disconnect_logs(self, websocket: WebSocket):
        """Disconnect a client from log streaming."""
        self.log_connections.discard(websocket)

    async def broadcast_progress(self, job_id: str, progress: SyncProgress):
        """Broadcast progress update to all connected clients for a job."""
        if job_id not in self.progress_connections:
            return

        message = progress.model_dump_json()
        dead_connections = set()

        for connection in self.progress_connections[job_id]:
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.progress_connections[job_id].discard(conn)

    async def broadcast_log(self, line: str):
        """Broadcast log line to all connected clients."""
        if not self.log_connections:
            return

        message = json.dumps({"line": line})
        dead_connections = set()

        for connection in self.log_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.log_connections.discard(conn)


# Global connection manager
manager = ConnectionManager()


# Register progress callback with sync manager
async def progress_callback(job_id: str, progress: SyncProgress):
    """Callback for sync manager to broadcast progress updates."""
    await manager.broadcast_progress(job_id, progress)


sync_manager.register_progress_callback(progress_callback)


@router.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job progress updates."""
    await manager.connect_progress(websocket, job_id)
    try:
        # Send current progress if available
        current_progress = sync_manager.get_progress(job_id)
        if current_progress:
            await websocket.send_text(current_progress.model_dump_json())

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for ping or close from client
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text("ping")

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_progress(websocket, job_id)


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await manager.connect_logs(websocket)
    try:
        # Stream logs
        async for line in log_streamer.stream_logs("container"):
            await websocket.send_text(json.dumps({"line": line}))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_logs(websocket)


@router.websocket("/ws/logs/{log_type}")
async def websocket_logs_typed(websocket: WebSocket, log_type: str):
    """WebSocket endpoint for streaming a specific log type."""
    await manager.connect_logs(websocket)
    try:
        async for line in log_streamer.stream_logs(log_type):
            await websocket.send_text(json.dumps({"line": line}))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_logs(websocket)
