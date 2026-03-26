"""
Hybrid Search Service
=====================
Three-stage search pipeline:

  Stage 1 — Keyword search
    Tokenises the query and scores each project across five fields:
    name, description, game_type, mechanics, framework.
    Every project with score > 0 is included as a keyword result.

  Stage 2 — Levenshtein fuzzy search
    Compares each token against every project name word using edit distance.
    Normalized similarity >= 0.75 counts as a match.
    Catches typos like "nigtth surval" -> "Night Survival".
    Only runs for projects NOT already found by keyword.

  Stage 3 — ML classifier search
    Predicts the game type from the query using the trained classifier.
    Finds projects whose design_doc.game_type matches the prediction.
    Only activates when classifier confidence >= 0.50.
    Results are added ONLY for projects not found by keyword or fuzzy.

Merge rule:
    Keyword > Fuzzy > ML (priority order).
    No project ever appears twice.
    Sorted by score descending.
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Stop words that appear in almost every game description — no discriminating value
_STOP_WORDS = {
    "a", "an", "the", "make", "build", "create", "game", "games",
    "i", "want", "with", "and", "or", "of", "to", "in", "for",
    "its", "my", "some", "where", "you", "your",
}

# Scoring weights per field
_WEIGHTS = {
    "name":        1.0,   # User named it — highest signal
    "description": 0.6,   # User described it — strong signal
    "game_type":   0.4,   # Stored game type label
    "mechanics":   0.3,   # Individual mechanics words
    "framework":   0.2,   # "phaser" or "godot"
}


_FUZZY_THRESHOLD = 0.75  # minimum similarity to count as a fuzzy match


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    m, n = len(s1), len(s2)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if s1[i - 1] == s2[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _fuzzy_similarity(s1: str, s2: str) -> float:
    """Normalized Levenshtein similarity 0.0 – 1.0."""
    if not s1 or not s2:
        return 0.0
    dist = _levenshtein(s1, s2)
    return 1.0 - dist / max(len(s1), len(s2))


def _fuzzy_score_project(tokens: list[str], project: dict) -> tuple[float, list[str]]:
    """
    Fuzzy-match tokens against project name words using Levenshtein.
    Each token is compared against every word in the project name.
    Best similarity per token is used; counts if >= _FUZZY_THRESHOLD.
    """
    name = project.get("name", "").lower()
    name_words = re.findall(r"[a-z0-9]+", name)
    if not name_words:
        return 0.0, []

    score = 0.0
    matched = set()

    for token in tokens:
        best_sim = max((_fuzzy_similarity(token, w) for w in name_words), default=0.0)
        if best_sim >= _FUZZY_THRESHOLD:
            score += _WEIGHTS["name"] * best_sim
            matched.add(token)

    return round(score, 4), list(matched)


def _contains(token: str, text: str) -> bool:
    """Word-boundary match — prevents 'car' matching 'arcade' or 'scar'."""
    return bool(re.search(r"\b" + re.escape(token) + r"\b", text))


def _tokenize(text: str) -> list[str]:
    """
    Lowercase, extract word tokens, drop stop words and single chars.
    "make a mario platformer" -> ["mario", "platformer"]
    """
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]


def _score_project(tokens: list[str], project: dict, raw_query: str = "") -> tuple[float, list[str]]:
    """
    Score a project against a list of query tokens.
    Returns (composite_score, list_of_matched_terms).

    Scoring priority:
      1. Exact name match (raw_query == name)       +3.0  — always ranks first
      2. Word-boundary token match in name          +1.0
      3. Substring token match in name (partial)    +0.5  — catches prefix/partial typing
      4. Exact game_type match bonus                +0.5  — e.g. searching "platformer"
      5. Other field matches (description, mechanics, framework)
    """
    name        = project.get("name", "").lower()
    description = project.get("description", "").lower()
    design      = project.get("design_doc") or {}
    game_type   = design.get("game_type", "").lower() if isinstance(design, dict) else ""
    mechanics   = " ".join(design.get("mechanics", [])).lower() if isinstance(design, dict) else ""
    framework   = project.get("framework", "").lower()

    score   = 0.0
    matched = set()

    # Exact name match — guaranteed top rank
    if raw_query and raw_query.lower() == name:
        score += 3.0
        matched.add(raw_query.lower())

    for token in tokens:
        hit = False
        if _contains(token, name):
            score += _WEIGHTS["name"]
            hit = True
        elif token in name:                   # partial/prefix match in name
            score += _WEIGHTS["name"] * 0.5
            hit = True
        if _contains(token, description):
            score += _WEIGHTS["description"]
            hit = True
        if _contains(token, game_type):
            score += _WEIGHTS["game_type"]
            hit = True
        if token == game_type:                # exact game_type match bonus
            score += 0.5
            hit = True
        if _contains(token, mechanics):
            score += _WEIGHTS["mechanics"]
            hit = True
        if _contains(token, framework):
            score += _WEIGHTS["framework"]
            hit = True
        if hit:
            matched.add(token)

    return round(score, 4), list(matched)


class HybridSearchService:

    def search(self, query: str, projects: list[dict[str, Any]]) -> dict:
        """
        Run hybrid search and return a result dict ready for the API response.

        Args:
            query:    Raw search string from the user.
            projects: List of project dicts (from storage.list_projects).

        Returns:
            {
                results: [{project, score, match_type, matched_terms}],
                query, total, keyword_hits, ml_hits,
                predicted_game_type, classifier_confidence
            }
        """
        query = query.strip()

        # Empty query — return all projects in their default sort order
        if not query:
            return {
                "results": [
                    {
                        "project":       p,
                        "score":         1.0,
                        "match_type":    "keyword",
                        "matched_terms": [],
                    }
                    for p in projects
                ],
                "query":                "",
                "total":                len(projects),
                "keyword_hits":         0,
                "ml_hits":              0,
                "predicted_game_type":  None,
                "classifier_confidence": None,
            }

        tokens = _tokenize(query)

        # If the entire query was stop words or too short, fall back to the raw
        # query as a single token so exact / substring name matches still work.
        if not tokens and len(query.strip()) >= 2:
            tokens = [query.strip().lower()]

        # ── Stage 1: Keyword search ────────────────────────────────────────────
        keyword_results: dict[str, dict] = {}

        if tokens:
            for project in projects:
                pid = project.get("project_id", "")
                score, matched = _score_project(tokens, project, raw_query=query.strip())
                if score > 0:
                    keyword_results[pid] = {
                        "project":       project,
                        "score":         score,
                        "match_type":    "keyword",
                        "matched_terms": matched,
                    }

        # ── Stage 2: Levenshtein fuzzy search ─────────────────────────────────
        fuzzy_results: dict[str, dict] = {}

        for project in projects:
            pid = project.get("project_id", "")
            if pid in keyword_results:
                continue  # already found by keyword
            score, matched = _fuzzy_score_project(tokens, project)
            if score > 0:
                fuzzy_results[pid] = {
                    "project":       project,
                    "score":         score,
                    "match_type":    "fuzzy",
                    "matched_terms": matched,
                }

        # ── Stage 3: ML classifier search ─────────────────────────────────────
        ml_results: dict[str, dict]  = {}
        predicted_game_type          = None
        classifier_confidence        = None

        # Skip classifier for very short queries — not enough signal
        if len(query) >= 3:
            try:
                from app.ml.classifier import predict_game_type, CONFIDENCE_THRESHOLD
                prediction            = predict_game_type(query)
                predicted_game_type   = prediction["game_type"]
                classifier_confidence = prediction["confidence"]
                needs_clarification   = prediction.get("needs_clarification", False)

                # Only add ML results when the model is confident
                if not needs_clarification and classifier_confidence >= CONFIDENCE_THRESHOLD:
                    # Boost ML score when keyword search found nothing — ML is the only signal
                    ml_score_multiplier = 0.80 if not keyword_results else 0.45
                    for project in projects:
                        pid    = project.get("project_id", "")
                        design = project.get("design_doc") or {}
                        if not isinstance(design, dict):
                            continue
                        proj_type = design.get("game_type", "")
                        if proj_type == predicted_game_type:
                            ml_results[pid] = {
                                "project":       project,
                                "score":         round(classifier_confidence * ml_score_multiplier, 4),
                                "match_type":    "game_type",
                                "matched_terms": [predicted_game_type],
                            }

            except Exception as exc:
                logger.warning("ML classifier search skipped: %s", exc)

        # ── Stage 4: Merge ────────────────────────────────────────────────────
        # Priority: keyword > fuzzy > ML
        merged: dict[str, dict] = dict(keyword_results)

        for pid, result in fuzzy_results.items():
            if pid not in merged:
                merged[pid] = result

        for pid, result in ml_results.items():
            if pid not in merged:
                merged[pid] = result

        # Sort by score descending
        sorted_results = sorted(
            merged.values(),
            key=lambda r: r["score"],
            reverse=True,
        )

        ml_hits    = sum(1 for r in sorted_results if r["match_type"] == "game_type")
        fuzzy_hits = sum(1 for r in sorted_results if r["match_type"] == "fuzzy")

        return {
            "results":               sorted_results,
            "query":                 query,
            "total":                 len(sorted_results),
            "keyword_hits":          len(keyword_results),
            "fuzzy_hits":            fuzzy_hits,
            "ml_hits":               ml_hits,
            "predicted_game_type":   predicted_game_type,
            "classifier_confidence": classifier_confidence,
        }


# Module-level singleton — imported by the route
search_service = HybridSearchService()
