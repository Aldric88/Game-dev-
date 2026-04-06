"""
Recommendation Service
======================
Builds a user preference vector from four signals:
  1. Game types the user has CREATED  (weight 3.0)
  2. Game types the user has LIKED    (weight 2.0)
  3. Game types from recent SEARCHES  (weight 1.0 × classifier confidence)
  4. Game types from recent PLAYS     (weight 1.5)

Also applies a K-Means cluster bonus (+1.0) for projects that share a
content cluster with any game the user has liked, created, or played.
This makes recommendations more specific than pure genre matching.

Scores every public project against that vector, then ranks by
(preference_score + cluster_bonus DESC, likes DESC).  Cold-start (no
signals) falls back to most-liked projects globally.
"""

from collections import defaultdict
from app.ml.bandit import bandit

_WEIGHTS = {
    "created":  3.0,
    "liked":    2.0,
    "searched": 1.0,
    "played":   1.5,
}

_CLUSTER_BONUS = 1.0   # added to score when project is in a preferred cluster


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
        play_history: list[dict] = [],
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

        # Signal 4 — played games
        for event in play_history[-20:]:
            gt = event.get("game_type")
            if gt:
                prefs[gt] += _WEIGHTS["played"]

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

        # ── K-Means cluster bonus ──────────────────────────────────────────────
        # Find which projects share a cluster with games the user has interacted with.
        # Seed projects = liked + created + recently played games.
        cluster_pids: set[str] = set()
        try:
            from app.ml.cluster_service import cluster_service
            all_dicts = [p if isinstance(p, dict) else dict(p) for p in public_projects]

            seed_ids = (
                {p.get("project_id") for p in liked_projects}
                | {p.get("project_id") for p in user_projects if p.get("is_public")}
                | {e.get("project_id") for e in play_history[-20:]}
            )

            for seed_id in seed_ids:
                if not seed_id:
                    continue
                similar = cluster_service.get_similar(seed_id, all_dicts, n=20)
                cluster_pids.update(p.get("project_id") for p in similar)
        except Exception:
            pass   # clustering is optional — fall back to genre-only gracefully

        def _score(p: dict) -> tuple[float, int]:
            gt            = (p.get("design_doc") or {}).get("game_type", "")
            genre_score   = prefs.get(gt, 0.0)
            cluster_bonus = _CLUSTER_BONUS if p.get("project_id") in cluster_pids else 0.0
            return (genre_score + cluster_bonus, p.get("likes", 0))

        ranked = sorted(candidates, key=_score, reverse=True)

        # ── Bandit re-ranking ──────────────────────────────────────────────────
        # Pass the top candidates through the epsilon-greedy bandit.
        # It keeps high win-rate games at the top (exploit) and randomly
        # promotes unseen games (explore) so new games get a fair chance.
        ranked = bandit.rank(user_id, ranked)

        return ranked[:limit]


recommendation_service = RecommendationService()


def record_feedback(user_id: str, project_id: str, liked: bool) -> None:
    """
    Call this whenever a user likes or ignores a recommended game.
    Feeds the result back into the bandit so it learns over time.

    Args:
        user_id    : The user who interacted.
        project_id : The game they interacted with.
        liked      : True if liked/played, False if ignored.
    """
    bandit.update(user_id, project_id, liked)
