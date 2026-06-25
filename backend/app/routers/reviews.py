"""
MergeMind — Reviews Router

Provides API endpoints for retrieving review results:
  • GET /review/{commit_sha} — Get review for a specific commit
  • GET /reviews/{github_username} — Get recent reviews for a user

These endpoints are consumed by the Chrome extension to display
review results on GitHub pages.
"""

import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Review
from app.schemas import ReviewResponse, ReviewListItem, ReviewSummary, ReviewIssue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])


@router.get("/review/{commit_sha}", response_model=ReviewResponse)
async def get_review_by_commit(
    commit_sha: str,
    db: Session = Depends(get_db),
):
    """
    Get the AI review results for a specific commit.
    
    This is the primary endpoint used by the Chrome extension.
    It returns the review status and results (if completed).
    
    The extension polls this endpoint while a review is in progress,
    showing a loading state until the status changes to 'completed'.
    
    Args:
        commit_sha: The Git commit SHA to look up
        
    Returns:
        ReviewResponse with status, summary, and issues
        
    Raises:
        404 if no review exists for the given commit
    """
    review = db.query(Review).filter(Review.commit_sha == commit_sha).first()

    if not review:
        raise HTTPException(
            status_code=404,
            detail="Error 404: No review found for this repository yet.",
        )

    return _build_review_response(review)


@router.post("/review/{review_id}/displayed", response_model=ReviewResponse)
async def mark_review_displayed(
    review_id: int,
    db: Session = Depends(get_db),
):
    """
    Mark a review as displayed to prevent auto-popup re-triggering.
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(
            status_code=404,
            detail="Error 404: No review found for this repository yet.",
        )
    review.displayed = True
    db.commit()
    db.refresh(review)
    return _build_review_response(review)

# 🟡 Are we using the following route??
@router.get("/reviews/{github_username}", response_model=list[ReviewListItem])
async def get_reviews_by_user(
    github_username: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max reviews to return"),
    repository: str = Query(default=None, description="Filter by repository full name (e.g., 'owner/repo')"),
    db: Session = Depends(get_db),
):
    """
    Get recent reviews for a GitHub user.
    
    Returns a compact list of reviews sorted by creation date (newest first).
    Useful for the extension popup to show review history.
    
    Args:
        github_username: GitHub username to look up
        limit: Maximum number of reviews to return (default: 20, max: 100)
        repository: Optional repository full name to filter by (e.g., "owner/repo")
        
    Returns:
        List of ReviewListItem objects
    """
    query = (
        db.query(Review)
        .filter(Review.github_username == github_username)
    )

    # Filter by repository if provided
    if repository:
        query = query.filter(Review.repository == repository)

    reviews = (
        query
        .order_by(Review.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for review in reviews:
        # Parse summary JSON if available
        summary = None
        if review.summary_json:
            try:
                summary_data = json.loads(review.summary_json)
                summary = ReviewSummary(**summary_data)
            except (json.JSONDecodeError, Exception):
                pass

        result.append(
            ReviewListItem(
                id=review.id,
                repository=review.repository,
                commit_sha=review.commit_sha,
                status=review.status,
                summary=summary,
                created_at=review.created_at,
            )
        )

    return result


@router.get("/review/repo/{repo_owner}/{repo_name}/latest", response_model=ReviewResponse)
async def get_latest_review_for_repo(
    repo_owner: str,
    repo_name: str,
    db: Session = Depends(get_db),
):
    """
    Get the latest review for a specific repository.
    
    Useful for the Chrome extension to show the most recent review
    when viewing a repository page (not a specific commit).
    
    Args:
        repo_owner: Repository owner (e.g., "octocat")
        repo_name: Repository name (e.g., "hello-world")
        
    Returns:
        ReviewResponse for the most recent review
        
    Raises:
        404 if no reviews exist for the given repository
    """
    repo_full_name = f"{repo_owner}/{repo_name}"

    review = (
        db.query(Review)
        .filter(Review.repository == repo_full_name)
        .order_by(Review.created_at.desc())
        .first()
    )

    if not review:
        raise HTTPException(
            status_code=404,
            detail="Error 404: No review found for this repository yet.",
        )

    return _build_review_response(review)


def _build_review_response(review: Review) -> ReviewResponse:
    """
    Helper to convert a Review ORM object into a ReviewResponse schema.
    
    Handles parsing the JSON fields (summary_json, issues_json)
    back into structured Pydantic models.
    """
    # Parse summary
    summary = None
    if review.summary_json:
        try:
            summary_data = json.loads(review.summary_json)
            summary = ReviewSummary(**summary_data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"⚠️ Failed to parse summary JSON for review {review.id}: {e}")

    # Parse issues
    issues = []
    if review.issues_json:
        try:
            issues_data = json.loads(review.issues_json)
            issues = [ReviewIssue(**issue) for issue in issues_data]
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"⚠️ Failed to parse issues JSON for review {review.id}: {e}")

    return ReviewResponse(
        id=review.id,
        github_username=review.github_username,
        github_user_id=review.github_user_id,
        repository=review.repository,
        commit_sha=review.commit_sha,
        status=review.status,
        summary=summary,
        issues=issues,
        error_message=review.error_message,
        displayed=review.displayed,
        created_at=review.created_at,
        completed_at=review.completed_at,
    )
