"""
MergeMind — SQLAlchemy ORM Models

Defines the database schema for storing code review results.
Each review is linked to a specific commit in a GitHub repository.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func
from app.database import Base


class Review(Base):
    """
    Stores a single AI code review for a GitHub commit.
    
    Lifecycle:
        1. Created with status='pending' when webhook is received
        2. Updated to status='processing' when agents start analyzing
        3. Updated to status='completed' with results when review finishes
        4. Updated to status='failed' if an error occurs during review
    """
    __tablename__ = "reviews"

    # ── Primary Key ───────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── GitHub Metadata ───────────────────────────────────────────────
    # The GitHub username who pushed the commit
    github_username = Column(String(255), nullable=False, index=True)

    # GitHub user ID (numeric) — useful for reliable identification
    github_user_id = Column(String(50), nullable=True)

    # Full repository name (e.g., "username/repo-name")
    repository = Column(String(500), nullable=False, index=True)

    # The commit SHA that triggered this review
    commit_sha = Column(String(40), nullable=False, unique=True, index=True)

    # ── Review Results ────────────────────────────────────────────────
    # Current status of the review pipeline
    # Values: "pending", "processing", "completed", "failed"
    status = Column(String(20), nullable=False, default="pending")

    # JSON string containing summary counts: {"bugs": 2, "security": 1, ...}
    summary_json = Column(Text, nullable=True)

    # JSON string containing the full list of issues found
    issues_json = Column(Text, nullable=True)

    # Error message if status is "failed"
    error_message = Column(Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────
    # When the webhook was received and the review record was created
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # When the review pipeline finished (completed or failed)
    completed_at = Column(DateTime, nullable=True)

    # Tracks whether the popup overlay has been displayed to the user
    displayed = Column(Boolean, nullable=False, default=False)

    def __repr__(self):
        return (
            f"<Review(id={self.id}, repo='{self.repository}', "
            f"commit='{self.commit_sha[:8]}...', status='{self.status}')>"
        )


class UserSettings(Base):
    """
    Stores per-user settings for the MergeMind review experience.
    
    Currently stores:
        - strictness: How strict the AI review should be
          ('lenient', 'moderate', or 'strict')
    """
    __tablename__ = "user_settings"

    github_username = Column(String(255), primary_key=True, index=True)
    strictness = Column(String(20), nullable=False, default="moderate")

