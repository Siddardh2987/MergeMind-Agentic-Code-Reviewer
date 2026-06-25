"""
MergeMind — Settings Router

Provides API endpoints for managing user settings:
  • GET /settings/{github_username} — Get user settings
  • POST /settings/{github_username} — Save user settings (strictness)

These are consumed by the Chrome extension popup to persist
the user's review strictness preference.
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


class UserSettingsRequest(BaseModel):
    """Request body for updating user settings."""
    strictness: str = Field(
        default="moderate",
        description="Review strictness: 'lenient', 'moderate', or 'strict'",
    )


class UserSettingsResponse(BaseModel):
    """Response for user settings."""
    github_username: str
    strictness: str = "moderate"

    class Config:
        from_attributes = True


@router.get("/settings/{github_username}", response_model=UserSettingsResponse)
async def get_user_settings(
    github_username: str,
    db: Session = Depends(get_db),
):
    """
    Get settings for a GitHub user.
    Returns defaults if no settings exist yet.
    """
    settings = (
        db.query(UserSettings)
        .filter(UserSettings.github_username == github_username)
        .first()
    )

    if not settings:
        return UserSettingsResponse(
            github_username=github_username,
            strictness="moderate",
        )

    return UserSettingsResponse(
        github_username=settings.github_username,
        strictness=settings.strictness,
    )


@router.post("/settings/{github_username}", response_model=UserSettingsResponse)
async def save_user_settings(
    github_username: str,
    body: UserSettingsRequest,
    db: Session = Depends(get_db),
):
    """
    Save settings for a GitHub user.
    Creates or updates the settings record.
    """
    # Validate strictness value
    valid_values = {"lenient", "moderate", "strict"}
    strictness = body.strictness if body.strictness in valid_values else "moderate"

    settings = (
        db.query(UserSettings)
        .filter(UserSettings.github_username == github_username)
        .first()
    )

    if settings:
        settings.strictness = strictness
    else:
        settings = UserSettings(
            github_username=github_username,
            strictness=strictness,
        )
        db.add(settings)

    db.commit()
    db.refresh(settings)

    logger.info(f"⚙️ Settings saved for {github_username}: strictness={strictness}")

    return UserSettingsResponse(
        github_username=settings.github_username,
        strictness=settings.strictness,
    )
