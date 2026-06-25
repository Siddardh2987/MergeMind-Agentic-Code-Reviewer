"""
MergeMind — Pydantic Schemas

Defines request/response models for the API.
These schemas handle validation, serialization, and documentation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════
# Review-Related Schemas
# ══════════════════════════════════════════════════════════════════════

class ReviewIssue(BaseModel):
    """
    A single issue found during code review.
    
    Example:
        {
            "category": "bug",
            "severity": "warning",
            "title": "Possible null reference",
            "description": "• Possible null access when repository metadata is unavailable."
        }
    """
    category: str = Field(
        ...,
        description="Issue category: 'bug', 'security', 'performance', or 'quality'"
    )
    severity: str = Field(
        ...,
        description="Issue severity: 'critical', 'warning', or 'info'"
    )
    title: str = Field(
        ...,
        max_length=80,
        description="Short issue title (max 80 chars)"
    )
    description: str = Field(
        ...,
        description="Concise explanation (100-250 chars), bullet-style"
    )


class ReviewSummary(BaseModel):
    """
    Summary counts of issues found across all categories.
    """
    bugs: int = Field(default=0, description="Number of bug issues found")
    security: int = Field(default=0, description="Number of security issues found")
    performance: int = Field(default=0, description="Number of performance issues found")
    quality: int = Field(default=0, description="Number of code quality issues found")


class ReviewResponse(BaseModel):
    """
    Complete review response returned by the API.
    
    This is the main response model that the Chrome extension consumes.
    """
    id: int
    github_username: str
    github_user_id: Optional[str] = None
    repository: str
    commit_sha: str
    status: str = Field(
        ...,
        description="Review status: 'pending', 'processing', 'completed', or 'failed'"
    )
    summary: Optional[ReviewSummary] = None
    issues: list[ReviewIssue] = Field(default_factory=list)
    error_message: Optional[str] = None
    displayed: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True  # Allows creating from SQLAlchemy model instances


class ReviewListItem(BaseModel):
    """
    Compact review info for listing multiple reviews.
    Used by the GET /reviews/{github_username} endpoint.
    """
    id: int
    repository: str
    commit_sha: str
    status: str
    summary: Optional[ReviewSummary] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════
# Webhook Schemas
# ══════════════════════════════════════════════════════════════════════

class WebhookResponse(BaseModel):
    """
    Response returned after receiving a webhook event.
    """
    message: str
    review_id: int
    commit_sha: str


# ══════════════════════════════════════════════════════════════════════
# Health Check Schema
# ══════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    """
    Response for the /health endpoint.
    """
    status: str = "ok"
    version: str = "1.0.0"
