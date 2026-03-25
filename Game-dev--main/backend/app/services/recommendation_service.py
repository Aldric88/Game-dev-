"""
Recommendation Service
======================
Builds a user preference vector from three signals:
  1. Game types the user has CREATED  (weight 3.0)
  2. Game types the user has LIKED    (weight 2.0)
  3. Game types from recent SEARCHES  (weight 1.0 × classifier confidence)

Scores every public project against that vector, then ranks by
(preference_score DESC, likes DESC).  Cold-start (no signals) falls
back to most-liked projects globally.
"""

from collections import defaultdict

_WEIGHTS = {
    "created":  3.0,
    "liked":    2.0,
    "searched": 1.0,
}


class RecommendationService:

    def recommend(
        self,
        user_id: str,
        user_projects: list[dict],
        liked_project_ids: list[str],
        liked_projects: list[dict],
        search_history: list[dict],
        public_projects: list[dict],
        limit: int = 10,
    ) -> list[dict]:
        """
        Return up to `limit` public projects personalised for the user.

        Args:
            user_id          : ID of the requesting user (to exclude own projects).
            user_projects    : All projects the user has created.
            liked_project_ids: IDs of public projects the user has liked.
            liked_projects   : Full docs of those liked projects.
            search_history   : Last N search events {predicted_game_type, confidence}.
            public_projects  : All public projects (pre-fetched, any order).
            limit            : Max results to return.
        """
        prefs: dict[str, float] = defaultdict(float)

        # Signal 1 — created games
        for p in user_projects:
            gt = (p.get("design_doc") or {}).get("game_type")
            if gt:
                prefs[gt] += _WEIGHTS["created"]

        # Signal 2 — liked games
        for p in liked_projects:
            gt = (p.get("design_doc") or {}).get("game_type")
            if gt:
                prefs[gt] += _WEIGHTS["liked"]

        # Signal 3 — search history (weighted by classifier confidence)
        for event in search_history[-20:]:
            gt   = event.get("predicted_game_type")
            conf = float(event.get("confidence", 0.5))
            if gt and conf >= 0.50:
                prefs[gt] += _WEIGHTS["searched"] * conf

        liked_set = set(liked_project_ids)

        # Exclude own projects and already-liked projects
        candidates = [
            p for p in public_projects
            if p.get("user_id") != user_id
            and p.get("project_id") not in liked_set
        ]

        # Cold start — no preference data yet, return most liked
        if not prefs:
            return sorted(candidates, key=lambda p: p.get("likes", 0), reverse=True)[:limit]

        def _score(p: dict) -> tuple[float, int]:
            gt = (p.get("design_doc") or {}).get("game_type", "")
            return (prefs.get(gt, 0.0), p.get("likes", 0))

        return sorted(candidates, key=_score, reverse=True)[:limit]


recommendation_service = RecommendationService()
