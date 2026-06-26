"""
MergeMind — Review Service

Orchestrates the complete AI review pipeline:
  1. Fetch diff from GitHub
  2. Build enriched code context
  3. Run all specialist agents in parallel
  4. Aggregate results
  5. Store final review in database

This is the core business logic of MergeMind.
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import Review, UserSettings
from app.services.github_service import fetch_commit_diff, fetch_files_content
from app.utils.diff_parser import parse_diff
from app.utils.context_builder import build_review_context, format_context_for_agent
from app.agents.code_quality import CodeQualityAgent
from app.agents.bug_detection import BugDetectionAgent
from app.agents.security import SecurityAgent
from app.agents.performance import PerformanceAgent
from app.agents.aggregator import AggregatorAgent
from app.services.ws_manager import manager as ws_manager

logger = logging.getLogger(__name__)


def _build_ws_payload(review: Review) -> dict:
    """
    Build a JSON-serializable dict from a Review ORM object
    for broadcasting over WebSocket.
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


async def run_review_pipeline(
    review_id: int,
    repo_full_name: str,
    commit_sha: str,
    db: Session,
) -> None:
    """
    Execute the full AI review pipeline for a commit.
    
    This function is called as a background task after the webhook
    endpoint receives a push event. It runs asynchronously so the
    webhook can return immediately.
    
    Pipeline steps:
    1. Update status to 'processing'
    2. Fetch the commit diff from GitHub
    3. Parse the diff into structured file changes
    4. Fetch full file contents for context enrichment
    5. Build enriched context (diff + surrounding functions)
    6. Run all 4 specialist agents in parallel
    7. Aggregate results into final review
    8. Store results and update status to 'completed'
    
    Args:
        review_id: Database ID of the review record
        repo_full_name: Full repository name (e.g., "owner/repo")
        commit_sha: The commit SHA being reviewed
        db: Database session
    """
    try:
        # ── Step 1: Mark as processing ────────────────────────────────
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            logger.error(f"❌ Review {review_id} not found in database")
            return

        review.status = "processing"
        db.commit()
        logger.info(f"🚀 Starting review pipeline for {repo_full_name}@{commit_sha[:8]}")

        # Notify WebSocket clients of processing status
        await ws_manager.notify_commit(commit_sha, _build_ws_payload(review))
        await ws_manager.notify_repo(repo_full_name, _build_ws_payload(review))

        # ── Step 1b: Read user strictness preference ──────────────────
        user_settings = (
            db.query(UserSettings)
            .filter(UserSettings.github_username == review.github_username)
            .first()
        )
        strictness = user_settings.strictness if user_settings else "moderate"
        logger.info(f"⚙️ Review strictness: {strictness}")

        # ── Step 2: Fetch the commit diff ─────────────────────────────
        raw_diff = await fetch_commit_diff(repo_full_name, commit_sha)
        if not raw_diff:
            await _mark_failed(review, db, "Failed to fetch commit diff from GitHub")
            return

        # ── Step 3: Parse the diff ────────────────────────────────────
        file_diffs = parse_diff(raw_diff)
        if not file_diffs:
            # No parseable file changes (might be binary-only or merge commits)
            await _mark_completed_empty(review, db)
            return

        logger.info(f"📂 Found changes in {len(file_diffs)} file(s)")

        # ── Step 4: Fetch full file contents for context ──────────────
        # Only fetch non-deleted, non-binary files
        file_paths = [
            fd.file_path
            for fd in file_diffs
            if not fd.is_deleted and not fd.is_binary
        ]
        file_contents = await fetch_files_content(
            repo_full_name, file_paths, commit_sha
        )

        # ── Step 5: Build enriched context ────────────────────────────
        file_contexts = build_review_context(file_diffs, file_contents)
        formatted_context = format_context_for_agent(file_contexts)

        # Guard: if context is too short, skip review
        if len(formatted_context) < 50:
            await _mark_completed_empty(review, db)
            return

        # ── Step 6: Run all agents in parallel ────────────────────────
        logger.info("🤖 Running specialist agents in parallel...")

        code_quality_agent = CodeQualityAgent()
        bug_detection_agent = BugDetectionAgent()
        security_agent = SecurityAgent()
        performance_agent = PerformanceAgent()

        # asyncio.gather runs all agents concurrently
        # This reduces total review time significantly

        # Concurrent Pipeline.
        results = await asyncio.gather(
            code_quality_agent.analyze(formatted_context, strictness=strictness),
            bug_detection_agent.analyze(formatted_context, strictness=strictness),
            security_agent.analyze(formatted_context, strictness=strictness),
            performance_agent.analyze(formatted_context, strictness=strictness),
            return_exceptions=True,
        )
        # Sequential Pipeline.
        # quality_result = await code_quality_agent.analyze(formatted_context, strictness=strictness)
        # bug_result = await bug_detection_agent.analyze(formatted_context, strictness=strictness)
        # security_result = await security_agent.analyze(formatted_context, strictness=strictness)
        # performance_result = await performance_agent.analyze(formatted_context, strictness=strictness)
        # results = quality_result+bug_result+security_result+performance_result

        # Collect all issues, handling any agent failures gracefully
        all_issues: list[dict] = []
        agent_names = ["Code Quality", "Bug Detection", "Security", "Performance"]
        failed_agents = []

        for agent_name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                logger.error(f"❌ {agent_name} agent raised an exception: {result}")
                failed_agents.append(f"{agent_name} ({str(result)})")
            elif isinstance(result, list):
                all_issues.extend(result)
            else:
                logger.warning(f"⚠️ {agent_name} agent returned unexpected type: {type(result)}")

        if failed_agents:
            raise RuntimeError(f"Specialist agent(s) failed: {', '.join(failed_agents)}")

        logger.info(f"🔍 Agents found {len(all_issues)} total issue(s) before aggregation")

        # ── Step 7: Aggregate results ─────────────────────────────────
        aggregator = AggregatorAgent()
        final_review = await aggregator.aggregate(all_issues, strictness=strictness)

        # ── Step 8: Store results ─────────────────────────────────────
        review.summary_json = json.dumps(final_review["summary"])
        review.issues_json = json.dumps(final_review["issues"])
        review.status = "completed"
        review.completed_at = datetime.now(timezone.utc)
        db.commit()

        total_issues = sum(final_review["summary"].values())
        logger.info(
            f"✅ Review complete for {repo_full_name}@{commit_sha[:8]}: "
            f"{total_issues} issue(s) found"
        )

        # Notify WebSocket clients of completion
        await ws_manager.notify_commit(commit_sha, _build_ws_payload(review))
        await ws_manager.notify_repo(repo_full_name, _build_ws_payload(review))

    except Exception as e:
        logger.exception(f"❌ Review pipeline failed: {str(e)}")
        try:
            review = db.query(Review).filter(Review.id == review_id).first()
            if review:
                await _mark_failed(review, db, str(e))
        except Exception:
            logger.exception("❌ Failed to update review status after error")


async def _mark_failed(review: Review, db: Session, error_msg: str) -> None:
    """Helper to mark a review as failed with an error message."""
    review.status = "failed"
    review.error_message = _format_error_message(error_msg)
    review.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.error(f"❌ Review {review.id} marked as failed: {review.error_message}")

    # Notify WebSocket clients of failure
    await ws_manager.notify_commit(review.commit_sha, _build_ws_payload(review))
    await ws_manager.notify_repo(review.repository, _build_ws_payload(review))


def _format_error_message(raw_error: str) -> str:
    """
    Convert a raw exception message into a clean, user-facing error string.

    Format: "Error <code>: <SOURCE> <DESCRIPTION>"

    Categories:
      - AI errors (rate limits, quota exhaustion, model failures)
      - GitHub errors (auth failures, API errors, diff fetch failures)
      - Internal errors (everything else)
    """
    err_lower = raw_error.lower()

    # ── AI / Gemini related errors ────────────────────────────────────
    if "429" in raw_error or "resource_exhausted" in err_lower or "resource exhausted" in err_lower:
        return "Error 429: AI RESOURCE EXHAUSTED. Please wait a moment and try again."
    elif "quota" in err_lower or "rate limit" in err_lower or "rate_limit" in err_lower:
        return "Error 429: AI RATE LIMIT EXCEEDED. Please try again later."
    elif "503" in raw_error and ("genai" in err_lower or "gemini" in err_lower or "model" in err_lower):
        return "Error 503: AI SERVICE UNAVAILABLE. The AI model is temporarily down."
    elif "gemini" in err_lower or "genai" in err_lower or "google.genai" in err_lower:
        return "Error 500: AI ANALYSIS FAILED. The AI model returned an unexpected error."
    elif "specialist agent" in err_lower:
        # Agents failed — check if it's an AI sub-error
        if "429" in raw_error or "resource_exhausted" in err_lower or "resource exhausted" in err_lower:
            return "Error 429: AI RESOURCE EXHAUSTED. Please wait a moment and try again."
        else:
            return "Error 500: AI ANALYSIS FAILED. One or more review agents encountered an error."

    # ── GitHub related errors ─────────────────────────────────────────
    elif "401" in raw_error and ("github" in err_lower or "unauthorized" in err_lower):
        return "Error 401: GITHUB UNAUTHORIZED. Check your GitHub token configuration."
    elif "403" in raw_error and ("github" in err_lower or "forbidden" in err_lower):
        return "Error 403: GITHUB FORBIDDEN. Your token may lack the required permissions."
    elif "404" in raw_error and "github" in err_lower:
        return "Error 404: GITHUB REPOSITORY NOT FOUND. Check that the repo exists and is accessible."
    elif "failed to fetch commit diff" in err_lower:
        return "Error 502: GITHUB DIFF FETCH FAILED. Could not retrieve the commit diff from GitHub."
    elif "github" in err_lower and ("token" in err_lower or "auth" in err_lower):
        return "Error 401: GITHUB AUTHENTICATION FAILED. Your GitHub token is invalid or expired."
    elif "github" in err_lower:
        return "Error 502: GITHUB API ERROR. Failed to communicate with the GitHub API."

    # ── Fallback ──────────────────────────────────────────────────────
    else:
        return "Error 500: INTERNAL SERVER ERROR. An unexpected error occurred during the review."



async def _mark_completed_empty(review: Review, db: Session) -> None:
    """Helper to mark a review as completed with no issues found."""
    review.status = "completed"
    review.summary_json = json.dumps({
        "bugs": 0, "security": 0, "performance": 0, "quality": 0
    })
    review.issues_json = json.dumps([])
    review.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"✅ Review {review.id} completed (no reviewable changes)")

    # Notify WebSocket clients of completion
    await ws_manager.notify_commit(review.commit_sha, _build_ws_payload(review))
    await ws_manager.notify_repo(review.repository, _build_ws_payload(review))
