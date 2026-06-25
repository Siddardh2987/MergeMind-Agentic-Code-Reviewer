"""
MergeMind — GitHub Service

Handles all interactions with the GitHub API:
  • Fetching commit diffs
  • Fetching full file contents for context
  • Validating webhook signatures

Uses httpx for async HTTP requests.
"""

import hmac
import hashlib
import logging
from typing import Optional
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"


def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """
    Verify that a webhook payload came from GitHub using HMAC-SHA256.
    
    GitHub sends a X-Hub-Signature-256 header with each webhook payload.
    We compute the expected signature using our shared secret and compare.
    
    Args:
        payload_body: Raw request body bytes
        signature: The X-Hub-Signature-256 header value (e.g., "sha256=abc...")
        
    Returns:
        True if the signature is valid, False otherwise
    """
    settings = get_settings()
    secret = settings.GITHUB_WEBHOOK_SECRET

    # If no secret is configured, skip validation (development mode)
    if not secret:
        logger.warning(
            "⚠️ GITHUB_WEBHOOK_SECRET is not set — skipping signature validation. "
            "This is insecure in production!"
        )
        return True

    # Compute expected signature
    expected_signature = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
    )

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)


async def fetch_commit_diff(repo_full_name: str, commit_sha: str) -> Optional[str]:
    """
    Fetch the diff for a specific commit from GitHub.
    
    Uses the GitHub API with the 'diff' media type to get the raw unified diff.
    
    Args:
        repo_full_name: Full repository name (e.g., "owner/repo")
        commit_sha: The commit SHA to fetch the diff for
        
    Returns:
        Raw unified diff string, or None if the request fails
    """
    settings = get_settings()
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits/{commit_sha}"

    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "MergeMind-Bot",
    }

    # Add auth token if available (increases rate limits from 60 to 5000 req/hr)
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            diff_content = response.text
            logger.info(
                f"📥 Fetched diff for {repo_full_name}@{commit_sha[:8]} "
                f"({len(diff_content)} chars)"
            )
            return diff_content

    except httpx.HTTPStatusError as e:
        logger.error(
            f"❌ GitHub API returned {e.response.status_code} for "
            f"{repo_full_name}@{commit_sha[:8]}: {e.response.text[:200]}"
        )
        return None
    except httpx.RequestError as e:
        logger.error(f"❌ Failed to connect to GitHub API: {str(e)}")
        return None


async def fetch_file_content(
    repo_full_name: str,
    file_path: str,
    commit_sha: str,
) -> Optional[str]:
    """
    Fetch the full content of a specific file at a specific commit.
    
    This is used by the context builder to get the complete file
    so we can extract surrounding function context.
    
    Args:
        repo_full_name: Full repository name (e.g., "owner/repo")
        file_path: Path to the file within the repo
        commit_sha: The commit SHA to fetch the file at
        
    Returns:
        File content as a string, or None if the request fails
    """
    settings = get_settings()
    url = (
        f"{GITHUB_API_BASE}/repos/{repo_full_name}"
        f"/contents/{file_path}?ref={commit_sha}"
    )

    headers = {
        # Request raw file content (not the JSON wrapper)
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "MergeMind-Bot",
    }

    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    except httpx.HTTPStatusError as e:
        # 404 is expected for deleted files — don't log as error
        if e.response.status_code == 404:
            logger.debug(f"File not found (may be deleted): {file_path}")
        else:
            logger.error(
                f"❌ Failed to fetch {file_path}: {e.response.status_code}"
            )
        return None
    except httpx.RequestError as e:
        logger.error(f"❌ Failed to connect to GitHub API: {str(e)}")
        return None


async def fetch_files_content(
    repo_full_name: str,
    file_paths: list[str],
    commit_sha: str,
) -> dict[str, str]:
    """
    Fetch content for multiple files concurrently.
    
    This is more efficient than fetching files one-by-one,
    especially for commits that touch many files.
    
    Args:
        repo_full_name: Full repository name
        file_paths: List of file paths to fetch
        commit_sha: Commit SHA to fetch files at
        
    Returns:
        Dict mapping file paths to their content (only successful fetches)
    """
    import asyncio

    results: dict[str, str] = {}

    # Limit concurrency to avoid hitting GitHub's rate limits
    semaphore = asyncio.Semaphore(5)

    async def fetch_single(path: str):
        async with semaphore:
            content = await fetch_file_content(repo_full_name, path, commit_sha)
            if content is not None:
                results[path] = content

    # Fetch all files concurrently (with semaphore limiting)
    tasks = [fetch_single(path) for path in file_paths]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(
        f"📥 Fetched {len(results)}/{len(file_paths)} file(s) for context"
    )
    return results
