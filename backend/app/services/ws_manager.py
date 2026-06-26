"""
MergeMind — WebSocket Connection Manager

Manages active WebSocket connections for real-time review status updates.
Clients can subscribe to:
  • A specific commit's review updates (keyed by commit SHA)
  • All review events for a repository (keyed by "owner/repo")

This is a singleton — import `manager` from this module.
"""

import logging
import asyncio
import json
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages pools of WebSocket connections for real-time notifications.

    Two connection pools:
      - commit_connections: clients watching a specific commit SHA
      - repo_connections: clients watching all reviews for a repo
    """

    def __init__(self):
        # commit_sha -> list of WebSocket connections
        self.commit_connections: dict[str, list[WebSocket]] = {}
        # "owner/repo" -> list of WebSocket connections
        self.repo_connections: dict[str, list[WebSocket]] = {}

    async def connect_commit(self, websocket: WebSocket, commit_sha: str):
        """Accept and register a WebSocket for a specific commit."""
        await websocket.accept()
        if commit_sha not in self.commit_connections:
            self.commit_connections[commit_sha] = []
        self.commit_connections[commit_sha].append(websocket)
        logger.info(f"🔌 WS connected for commit {commit_sha[:8]} "
                    f"(total: {len(self.commit_connections[commit_sha])})")

    async def connect_repo(self, websocket: WebSocket, repo_full_name: str):
        """Accept and register a WebSocket for a repository."""
        await websocket.accept()
        if repo_full_name not in self.repo_connections:
            self.repo_connections[repo_full_name] = []
        self.repo_connections[repo_full_name].append(websocket)
        logger.info(f"🔌 WS connected for repo {repo_full_name} "
                    f"(total: {len(self.repo_connections[repo_full_name])})")

    def disconnect_commit(self, websocket: WebSocket, commit_sha: str):
        """Remove a WebSocket from the commit pool."""
        if commit_sha in self.commit_connections:
            try:
                self.commit_connections[commit_sha].remove(websocket)
            except ValueError:
                pass
            if not self.commit_connections[commit_sha]:
                del self.commit_connections[commit_sha]
            logger.info(f"🔌 WS disconnected from commit {commit_sha[:8]}")

    def disconnect_repo(self, websocket: WebSocket, repo_full_name: str):
        """Remove a WebSocket from the repo pool."""
        if repo_full_name in self.repo_connections:
            try:
                self.repo_connections[repo_full_name].remove(websocket)
            except ValueError:
                pass
            if not self.repo_connections[repo_full_name]:
                del self.repo_connections[repo_full_name]
            logger.info(f"🔌 WS disconnected from repo {repo_full_name}")

    async def notify_commit(self, commit_sha: str, data: dict):
        """
        Broadcast a message to all clients watching a specific commit.

        Stale connections are automatically removed on send failure.
        """
        connections = self.commit_connections.get(commit_sha, [])
        if not connections:
            return

        stale = []
        message = json.dumps(data)

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                stale.append(ws)

        # Clean up broken connections
        for ws in stale:
            try:
                self.commit_connections[commit_sha].remove(ws)
            except (ValueError, KeyError):
                pass

        if connections:
            logger.info(f"📡 Notified {len(connections) - len(stale)} client(s) "
                        f"for commit {commit_sha[:8]}")

    async def notify_repo(self, repo_full_name: str, data: dict):
        """
        Broadcast a message to all clients watching a repository.

        Stale connections are automatically removed on send failure.
        """
        connections = self.repo_connections.get(repo_full_name, [])
        if not connections:
            return

        stale = []
        message = json.dumps(data)

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                stale.append(ws)

        # Clean up broken connections
        for ws in stale:
            try:
                self.repo_connections[repo_full_name].remove(ws)
            except (ValueError, KeyError):
                pass

        if connections:
            logger.info(f"📡 Notified {len(connections) - len(stale)} client(s) "
                        f"for repo {repo_full_name}")


# ── Singleton Instance ────────────────────────────────────────────────
# Import this directly: `from app.services.ws_manager import manager`
manager = ConnectionManager()
