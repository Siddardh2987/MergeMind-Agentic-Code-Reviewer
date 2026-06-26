"""
MergeMind — Webhook Router

Handles incoming GitHub webhook events.
The main endpoint is POST /webhook which:
  1. Validates the webhook signature (HMAC-SHA256)
  2. Extracts commit metadata from the payload
  3. Creates a pending review record
  4. Launches the AI review pipeline as a background task
"""

import json
import logging
import asyncio
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Review
from app.schemas import WebhookResponse
from app.services.github_service import verify_webhook_signature
from app.services.review_service import run_review_pipeline
from app.services.ws_manager import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook", response_model=WebhookResponse)
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive and process GitHub webhook push events.
    
    GitHub sends a POST request to this endpoint whenever a push occurs
    on a repository that has the webhook configured.
    
    The webhook payload contains:
    - repository info (name, full_name, owner)
    - commit details (SHA, message, author)
    - pusher info (username)
    
    We validate the signature, extract the relevant data, create a
    pending review record, and launch the review pipeline in the background.
    """
    # ── Step 1: Read and validate the raw request body ────────────────
    raw_body = await request.body()

    # Verify GitHub's HMAC-SHA256 signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_webhook_signature(raw_body, signature):
        logger.warning("🚫 Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Error 401: Authentication failed.")

    # ── Step 2: Parse the JSON payload ────────────────────────────────
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Error 400: Invalid request sent to the backend.")

    # ── Step 3: Check event type ──────────────────────────────────────
    # We only process push events
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "push":
        logger.info(f"ℹ️ Ignoring non-push event: {event_type}")
        return WebhookResponse(
            message=f"Event '{event_type}' ignored (only push events are processed)",
            review_id=0,
            commit_sha="",
        )

    # ── Step 4: Extract metadata from payload ─────────────────────────
    # Get the head commit SHA (the latest commit in the push)
    head_commit = payload.get("head_commit")
    if not head_commit:
        raise HTTPException(
            status_code=400,
            detail="Error 400: Invalid request sent to the backend."
        )

    commit_sha = head_commit.get("id", "")
    if not commit_sha:
        raise HTTPException(status_code=400, detail="Error 400: Invalid request sent to the backend.")

    # Repository info
    repo_info = payload.get("repository", {})
    repo_full_name = repo_info.get("full_name", "")

    # Pusher info (the person who pushed)
    pusher = payload.get("pusher", {})
    github_username = pusher.get("name", "unknown")

    # Sender info (contains user ID)
    # 🟡 What does sender even do??
    sender = payload.get("sender", {})
    github_user_id = str(sender.get("id", "")) if sender.get("id") else None

    logger.info(
        f"📨 Received push event: {repo_full_name}@{commit_sha[:8]} "
        f"by {github_username}"
    )

    # ── Step 5: Check for duplicate review ────────────────────────────
    existing = db.query(Review).filter(Review.commit_sha == commit_sha).first()
    if existing:
        logger.info(f"ℹ️ Review already exists for commit {commit_sha[:8]}")
        return WebhookResponse(
            message="Review already exists for this commit",
            review_id=existing.id,
            commit_sha=commit_sha,
        )

    # ── Step 6: Create pending review record ──────────────────────────
    review = Review(
        github_username=github_username,
        github_user_id=github_user_id,
        repository=repo_full_name,
        commit_sha=commit_sha,
        status="pending",
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    logger.info(f"📝 Created review record #{review.id} (status: pending)")

    # ── Step 6b: Notify WebSocket subscribers of new review ───────────
    payload = {
        "id": review.id,
        "github_username": review.github_username,
        "github_user_id": github_user_id,
        "repository": review.repository,
        "commit_sha": review.commit_sha,
        "status": review.status,
        "summary": None,
        "issues": [],
        "error_message": None,
        "displayed": review.displayed,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "completed_at": None,
    }
    await ws_manager.notify_commit(commit_sha, payload)
    await ws_manager.notify_repo(repo_full_name, payload)

    # ── Step 7: Launch review pipeline in background ──────────────────
    # We create a new database session for the background task
    # because the request's session will be closed after the response
    asyncio.create_task(
        _run_review_in_background(review.id, repo_full_name, commit_sha)
    )

    return WebhookResponse(
        message="Review started! 🚀 Check back in a moment.",
        review_id=review.id,
        commit_sha=commit_sha,
    )


async def _run_review_in_background(
    review_id: int,
    repo_full_name: str,
    commit_sha: str,
) -> None:
    """
    Wrapper that creates a fresh DB session for the background review task.
    
    We need a separate session because the request's session
    is closed after the webhook response is sent.
    """
    # Create a new session for the background task
    db = SessionLocal()
    try:
        await run_review_pipeline(review_id, repo_full_name, commit_sha, db)
    except Exception as e:
        logger.exception(f"❌ Background review task failed: {str(e)}")
    finally:
        db.close()
