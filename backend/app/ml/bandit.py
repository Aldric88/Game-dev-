"""
Epsilon-Greedy Bandit
=====================
A simple reinforcement learning algorithm that learns which games to recommend
to each user by trial and error.

How it works:
- Every time a game is shown to a user, it's a "trial"
- Every time a user likes a game, it's a "win"
- Win rate = wins / trials  →  higher = show more
- Epsilon (20%): sometimes show a random game to explore new ones
- (1 - Epsilon) (80%): show games with highest win rate (exploit)

No external libraries — implemented from scratch using pure Python.
"""

import random


# 20% of the time explore (show random game), 80% exploit (show best known game)
_EPSILON = 0.2

# Win rate assigned to games never shown before (optimistic — encourages exploration)
_DEFAULT_WIN_RATE = 0.5


class EpsilonGreedyBandit:
    """
    Per-user Epsilon-Greedy Bandit for game recommendation ranking.

    Internal state (in-memory):
        _trials[user_id][project_id] = number of times game was shown to user
        _wins[user_id][project_id]   = number of times user liked the game
    """

    def __init__(self, epsilon: float = _EPSILON):
        self.epsilon = epsilon
        self._trials: dict[str, dict[str, int]] = {}   # user → project → count
        self._wins:   dict[str, dict[str, int]] = {}   # user → project → count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, user_id: str, project_id: str, liked: bool) -> None:
        """
        Call this when a user interacts with a recommended game.

        Args:
            user_id    : The user who was shown the game.
            project_id : The game that was shown.
            liked      : True if the user liked/played it, False if ignored.
        """
        if user_id not in self._trials:
            self._trials[user_id] = {}
            self._wins[user_id]   = {}

        self._trials[user_id][project_id] = self._trials[user_id].get(project_id, 0) + 1
        if liked:
            self._wins[user_id][project_id] = self._wins[user_id].get(project_id, 0) + 1

    def rank(self, user_id: str, candidates: list[dict]) -> list[dict]:
        """
        Re-rank candidate games for a user using epsilon-greedy strategy.

        Args:
            user_id    : The user to rank games for.
            candidates : List of project dicts (already filtered by recommendation_service).

        Returns:
            Re-ranked list — exploited games first, with random exploration mixed in.
        """
        if not candidates:
            return candidates

        exploit, explore = self._split(user_id, candidates)

        # Build final ranked list:
        # - Exploit bucket: sorted by win rate (best first)
        # - Explore bucket: shuffled randomly
        ranked = exploit + explore
        return ranked

    def win_rate(self, user_id: str, project_id: str) -> float:
        """Return win rate for a (user, game) pair. Returns default if never shown."""
        trials = self._trials.get(user_id, {}).get(project_id, 0)
        if trials == 0:
            return _DEFAULT_WIN_RATE
        wins = self._wins.get(user_id, {}).get(project_id, 0)
        return wins / trials

    def stats(self, user_id: str, project_id: str) -> dict:
        """Return debug stats for a (user, game) pair."""
        trials = self._trials.get(user_id, {}).get(project_id, 0)
        wins   = self._wins.get(user_id, {}).get(project_id, 0)
        return {
            "trials":   trials,
            "wins":     wins,
            "win_rate": self.win_rate(user_id, project_id),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split(self, user_id: str, candidates: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Split candidates into exploit and explore buckets.

        Each candidate independently goes to explore bucket with probability epsilon,
        otherwise goes to exploit bucket (sorted by win rate descending).
        """
        exploit_bucket = []
        explore_bucket = []

        for game in candidates:
            pid = game.get("project_id", "")
            if random.random() < self.epsilon:
                # Explore — try this game regardless of past performance
                explore_bucket.append(game)
            else:
                # Exploit — rank by known win rate
                exploit_bucket.append((self.win_rate(user_id, pid), game))

        # Sort exploit bucket by win rate descending
        exploit_bucket.sort(key=lambda x: x[0], reverse=True)
        exploit_games  = [game for _, game in exploit_bucket]

        # Shuffle explore bucket for randomness
        random.shuffle(explore_bucket)

        return exploit_games, explore_bucket


# Singleton — shared across the app
bandit = EpsilonGreedyBandit()
