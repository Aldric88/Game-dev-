"""
GitHub Repository Search Service
==================================
Searches GitHub for open-source game projects that match the user's
game type and framework. Results are used as reference code by the AI
orchestrator to produce higher-quality, more idiomatic games.

Framework-aware query strategy:
  phaser   → language:javascript "phaser"
  godot    → language:gdscript "godot"
  fallback → topic:game  (any language)

Only MIT / Apache-2.0 licensed repos are considered.
Sorted by stars (best community-validated code first).
Capped at 3 results to keep context window overhead low.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# GitHub REST API base
_GH_API = "https://api.github.com"

# Max repos to return (more = more context token cost)
_MAX_REPOS = 3

# Seconds before we give up and skip GitHub enrichment
_TIMEOUT = 6.0

# Map framework names → GitHub search language filters
_FRAMEWORK_LANG: dict[str, str] = {
    "phaser":   "javascript",
    "godot":    "gdscript",
    "pygame":   "python",
    "unity":    "csharp",
    "canvas":   "javascript",
}

# Map game_type → search keywords that improve relevance
_GAME_TYPE_KEYWORDS: dict[str, str] = {
    "platformer":    "platformer",
    "shooter":       "shooter game",
    "space_shooter": "space shooter",
    "racing":        "racing game",
    "puzzle":        "puzzle game",
    "rpg":           "rpg game",
    "tower_defense": "tower defense",
    "flappy":        "flappy bird",
    "snake":         "snake game",
    "fighting":      "fighting game",
    "survival":      "survival game",
    "topdown":       "top down game",
    "arcade":        "arcade game",
}


def _build_query(game_type: str, framework: str) -> str:
    """Build a GitHub code search query string."""
    keyword = _GAME_TYPE_KEYWORDS.get(game_type, f"{game_type} game")
    lang = _FRAMEWORK_LANG.get(framework.lower(), "")

    parts = [f'"{keyword}"', "topic:game"]
    if lang:
        parts.append(f"language:{lang}")
    # Only open-source permissive licenses
    parts.append("license:mit OR license:apache-2.0")

    return " ".join(parts)


async def search_similar_repos(
    game_type: str,
    framework: str,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search GitHub for repos similar to the requested game.

    Returns a list of dicts:
        {
            "full_name":       "owner/repo",
            "description":     "...",
            "stars":           1234,
            "default_branch":  "main",
            "html_url":        "https://github.com/...",
            "framework":       "phaser",
        }

    Returns [] on any error so that caller is never blocked.
    """
    token = token or os.getenv("GITHUB_TOKEN", "")
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    query = _build_query(game_type, framework)
    params = {
        "q":        query,
        "sort":     "stars",
        "order":    "desc",
        "per_page": str(_MAX_REPOS),
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_GH_API}/search/repositories",
                headers=headers,
                params=params,
            )
            if resp.status_code == 403:
                logger.warning("GitHub rate limit hit — skipping enrichment")
                return []
            if not resp.is_success:
                logger.warning("GitHub search returned %s", resp.status_code)
                return []

            data = resp.json()
            repos = []
            for item in data.get("items", [])[:_MAX_REPOS]:
                repos.append({
                    "full_name":      item["full_name"],
                    "description":    item.get("description") or "",
                    "stars":          item.get("stargazers_count", 0),
                    "default_branch": item.get("default_branch", "main"),
                    "html_url":       item.get("html_url", ""),
                    "framework":      framework,
                })
            logger.info(
                "GitHub search '%s' → %d repo(s) found",
                query[:80],
                len(repos),
            )
            return repos

    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("GitHub search failed (network): %s", exc)
        return []
    except Exception as exc:
        logger.warning("GitHub search failed: %s", exc)
        return []
