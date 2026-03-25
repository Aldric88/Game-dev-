"""
GitHub Code Extractor
======================
Downloads the most relevant source files from a GitHub repository and
returns a compact, token-budget-aware text snippet for the AI prompt.

File priority (highest → lowest):
  index.html, game.js, main.js, src/game.js, src/main.js,
  src/index.js, app.js, README.md

Each file is trimmed to _MAX_CHARS_PER_FILE characters.
The combined output is capped at _MAX_TOTAL_CHARS characters.
Both limits keep context-window overhead manageable.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RAW_BASE = "https://raw.githubusercontent.com"

_CANDIDATE_FILES = [
    "index.html",
    "game.js",
    "main.js",
    "src/game.js",
    "src/main.js",
    "src/index.js",
    "app.js",
    "README.md",
]

# Per-file character budget
_MAX_CHARS_PER_FILE = 1_500

# Total budget across all files
_MAX_TOTAL_CHARS = 4_000

# HTTP timeout per file request
_TIMEOUT = 5.0


async def _fetch_raw(
    client: httpx.AsyncClient,
    full_name: str,
    branch: str,
    filepath: str,
) -> str | None:
    """Fetch raw file content; return None on any error."""
    url = f"{_RAW_BASE}/{full_name}/{branch}/{filepath}"
    try:
        resp = await client.get(url, timeout=_TIMEOUT)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def _trim(content: str, max_chars: int) -> str:
    """Trim content to max_chars, appending a truncation note."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n... [truncated]"


async def extract_game_code(repo: dict[str, Any]) -> str:
    """
    Download relevant files from a repo and return a combined code snippet.

    Args:
        repo: dict with keys full_name, default_branch, html_url, description

    Returns:
        A formatted multi-file code string, or "" if nothing could be fetched.
    """
    full_name = repo.get("full_name", "")
    branch    = repo.get("default_branch", "main")
    url       = repo.get("html_url", "")
    desc      = repo.get("description", "")
    stars     = repo.get("stars", 0)

    if not full_name:
        return ""

    sections: list[str] = []
    total_chars = 0

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for filepath in _CANDIDATE_FILES:
            if total_chars >= _MAX_TOTAL_CHARS:
                break

            content = await _fetch_raw(client, full_name, branch, filepath)
            if not content:
                continue

            remaining = _MAX_TOTAL_CHARS - total_chars
            trimmed = _trim(content, min(_MAX_CHARS_PER_FILE, remaining))
            sections.append(f"// --- {filepath} ---\n{trimmed}")
            total_chars += len(trimmed)

    if not sections:
        return ""

    header = (
        f"// Source: {url}\n"
        f"// Repo:   {full_name}  ({stars} stars)\n"
        f"// Desc:   {desc}\n\n"
    )
    return header + "\n\n".join(sections)


async def fetch_reference_code(repos: list[dict[str, Any]]) -> str:
    """
    Fetch code from the best available repo (tries repos in order).

    Returns the first non-empty result, or "" if all fail.
    """
    for repo in repos:
        code = await extract_game_code(repo)
        if code.strip():
            logger.info(
                "Fetched reference code from %s (%d chars)",
                repo.get("full_name"),
                len(code),
            )
            return code
    return ""
