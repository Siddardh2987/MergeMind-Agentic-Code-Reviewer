"""
MergeMind — WebSocket Router

Provides real-time WebSocket endpoints that replace the extension's
polling loops:

  • WS /ws/review/{commit_sha}  — subscribe to a specific commit's review updates
  • WS /ws/repo/{owner}/{repo}  — subscribe to all review events for a repository

On connect, the current review state is sent immediately. Subsequent
messages are pushed whenever the review status changes (triggered by
the review pipeline or webhook handler).
"""

import json
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Review
from app.services.ws_manager import manager
from app.schemas import ReviewResponse, ReviewSummary, ReviewIssue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


def _build_review_dict(review: Review) -> dict:
    """
    Convert a Review ORM object into a JSON-serializable dict
    matching the ReviewResponse schema shape.
    """
    summary = None
    if review.summary_json:
        try:
            summary = json.loads(review.summary_json)
        except (json.JSONDecodeError, Exception):
            pass

    issues = []
    if review.issues_json:
        try:
            issues = json.loads(review.issues_json)
        except (json.JSONDecodeError, Exception):
            pass

    return {
        "id": review.id,
        "github_username": review.github_username,
        "github_user_id": review.github_user_id,
        "repository": review.repository,
        "commit_sha": review.commit_sha,
        "status": review.status,
        "summary": summary,
        "issues": issues,
        "error_message": review.error_message,
        "displayed": review.displayed,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
    }


@router.websocket("/ws/review/{commit_sha}")
async def ws_review_by_commit(websocket: WebSocket, commit_sha: str):
    """
    WebSocket endpoint for subscribing to a specific commit's review.

    On connect:
      - Sends the current review state (or {"status": "not_found"})
    On update:
      - Server pushes new state whenever the review status changes
    """
    await manager.connect_commit(websocket, commit_sha)

    # Send current state immediately
    db = SessionLocal()
    try:
        review = db.query(Review).filter(Review.commit_sha == commit_sha).first()
        if review:
            await websocket.send_text(json.dumps(_build_review_dict(review)))
        else:
            await websocket.send_text(json.dumps({"status": "not_found"}))
    except Exception as e:
        logger.error(f"❌ WS initial state error: {e}")
    finally:
        db.close()

    # Keep connection alive — wait for client messages or disconnect
    try:
        while True:
            # We don't expect meaningful messages from the client,
            # but we need to await receive to detect disconnections.
            # The client can send "ping" and we reply "pong" for keep-alive.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect_commit(websocket, commit_sha)
    except Exception:
        manager.disconnect_commit(websocket, commit_sha)


@router.websocket("/ws/repo/{repo_owner}/{repo_name}")
async def ws_review_by_repo(websocket: WebSocket, repo_owner: str, repo_name: str):
    """
    WebSocket endpoint for subscribing to all review events in a repo.

    On connect:
      - Sends the latest review state (or {"status": "not_found"})
    On update:
      - Server pushes whenever a new review is created or status changes
    """
    repo_full_name = f"{repo_owner}/{repo_name}"
    await manager.connect_repo(websocket, repo_full_name)

    # Send current latest review state immediately
    db = SessionLocal()
    try:
        review = (
            db.query(Review)
            .filter(Review.repository == repo_full_name)
            .order_by(Review.created_at.desc())
            .first()
        )
        if review:
            await websocket.send_text(json.dumps(_build_review_dict(review)))
        else:
            await websocket.send_text(json.dumps({"status": "not_found"}))
    except Exception as e:
        logger.error(f"❌ WS initial state error: {e}")
    finally:
        db.close()

    # Keep connection alive
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect_repo(websocket, repo_full_name)
    except Exception:
        manager.disconnect_repo(websocket, repo_full_name)
