"""
MergeMind — Configuration Management

Loads and validates all environment variables using pydantic-settings.
Each variable is documented with its purpose and default value.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via a .env file in the backend/ directory
    or by setting environment variables directly.
    """

    # ── Gemini Configuration ─────────────────────────────────────────
    GEMINI_API_KEY: str =""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # ── GitHub Configuration ──────────────────────────────────────────
    # Secret used to validate incoming webhook payloads (HMAC-SHA256)
    GITHUB_WEBHOOK_SECRET: str = ""

    # Personal access token for fetching diffs and file contents via GitHub API
    GITHUB_TOKEN: str = ""

    # ── Database Configuration ────────────────────────────────────────
    # SQLite database file path (relative to backend/ directory)
    DATABASE_URL: str = "sqlite:///./mergemind.db"

    # ── Server Configuration ──────────────────────────────────────────
    # Backend URL (used for CORS and documentation)
    BACKEND_URL: str = "https://mergemind-agentic-code-reviewer.onrender.com"

    # Allowed CORS origins (comma-separated) — Chrome extension needs this
    CORS_ORIGINS: str = "chrome-extension://*,http://localhost:3000"

    class Config:
        # Load variables from .env file in the backend directory
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    
    Using lru_cache ensures we only read the .env file once,
    and all subsequent calls return the same Settings object.
    """
    return Settings()
