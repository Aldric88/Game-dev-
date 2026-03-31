"""
K-Means Cluster Service
=======================
Groups public projects by content similarity using TF-IDF + K-Means.

Used for:
  1. "Similar Games" — given a project, return others in the same cluster.
  2. Smarter recommendations — score clusters instead of raw genres.

How it works:
  - Each project is converted to a TF-IDF vector (name, game_type, mechanics, description).
  - KMeans groups them into N clusters based on content similarity.
  - Projects in the same cluster share similar themes, mechanics, and descriptions.

Fitting:
  - Lazy: fits on first request, refits if a new project is not yet indexed.
  - No labels needed — fully unsupervised.
  - Minimum 5 projects required to form meaningful clusters.
"""

import logging
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

_N_CLUSTERS  = 15   # max clusters — auto-reduced for small datasets
_MIN_PROJECTS = 5   # minimum projects needed to cluster


class ClusterService:

    def __init__(self):
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=500,
            stop_words="english",
        )
        self._kmeans: KMeans | None = None
        self._project_ids: list[str] = []
        self._labels: list[int]      = []

    def _text(self, project: dict) -> str:
        """Build a single text string for a project (name weighted double)."""
        name      = project.get("name", "")
        desc      = project.get("description", "") or ""
        design    = project.get("design_doc") or {}
        game_type = design.get("game_type", "") if isinstance(design, dict) else ""
        mechanics = " ".join(design.get("mechanics", [])) if isinstance(design, dict) else ""
        return f"{name} {name} {game_type} {mechanics} {desc}"

    def fit(self, projects: list[dict]) -> bool:
        """
        Fit K-Means on all given projects.
        Returns True if successful, False if not enough data.
        """
        if len(projects) < _MIN_PROJECTS:
            logger.info("Not enough projects to cluster (%d < %d)", len(projects), _MIN_PROJECTS)
            return False
        try:
            texts      = [self._text(p) for p in projects]
            n_clusters = min(_N_CLUSTERS, max(2, len(projects) // 2))
            X          = self._vectorizer.fit_transform(texts)

            self._kmeans      = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            self._labels      = self._kmeans.fit_predict(X).tolist()
            self._project_ids = [p.get("project_id", "") for p in projects]

            logger.info("K-Means fitted: %d projects → %d clusters", len(projects), n_clusters)
            return True
        except Exception as exc:
            logger.error("K-Means fit failed: %s", exc)
            return False

    def get_similar(self, project_id: str, projects: list[dict], n: int = 6) -> list[dict]:
        """
        Return up to n projects in the same cluster as project_id.
        Refits automatically if the project is not yet indexed.
        Falls back to empty list if clustering is not possible.
        """
        # Refit if not fitted yet, or if this project wasn't in the last fit
        if self._kmeans is None or project_id not in self._project_ids:
            if not self.fit(projects):
                return []

        if project_id not in self._project_ids:
            return []

        idx     = self._project_ids.index(project_id)
        cluster = self._labels[idx]

        pid_map = {p.get("project_id"): p for p in projects}
        similar = [
            pid_map[self._project_ids[i]]
            for i, label in enumerate(self._labels)
            if label == cluster
            and self._project_ids[i] != project_id
            and self._project_ids[i] in pid_map
        ]

        # Sort by likes descending so best games surface first
        similar.sort(key=lambda p: p.get("likes", 0), reverse=True)
        return similar[:n]


cluster_service = ClusterService()
