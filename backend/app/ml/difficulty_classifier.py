"""
Game Difficulty Classifier
==========================
Algorithm : Multi-class Perceptron (implemented from scratch — no sklearn)
Task      : Classify a generated game as Easy | Medium | Hard
Features  : 5 hand-engineered features from the game design document

How the Perceptron works
------------------------
A perceptron is the simplest ML classifier. It learns a weight for each
feature. To predict, it multiplies each feature by its weight and sums them.

For multi-class (3 labels), we use One-vs-Rest:
  - Three separate perceptrons: one per class
  - Each perceptron answers "is this game Easy/Medium/Hard?"
  - The class with the highest score wins

Training (Perceptron learning rule):
  For each training example:
    1. Predict the class using current weights
    2. If wrong:  winner weights  -= learning_rate * features
                  correct weights += learning_rate * features
    3. Repeat for N epochs

No external ML libraries used — only pure Python + basic math.

Features extracted from design_doc
-----------------------------------
  1. mechanic_count  — how many mechanics (normalized 0-1, cap 10)
  2. entity_count    — how many entities (normalized 0-1, cap 12)
  3. has_boss        — boss fight present (0 or 1)
  4. has_upgrades    — upgrade/level-up system present (0 or 1)
  5. has_hazards     — dodge/trap/hazard mechanic present (0 or 1)

Difficulty intuition
---------------------
  Easy   → few mechanics, few entities, no boss, no upgrades, no hazards
  Medium → moderate mechanics/entities, maybe upgrades or hazards, no boss
  Hard   → many mechanics, many entities, has boss, has upgrades, has hazards
"""

from __future__ import annotations

import random
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Keyword sets for feature extraction ──────────────────────────────────────

_BOSS_KEYWORDS    = {"boss", "final boss", "boss fight", "boss battle", "miniboss"}
_UPGRADE_KEYWORDS = {"upgrade", "level up", "level-up", "skill tree", "evolve",
                     "power up", "powerup", "prestige", "xp", "experience"}
_HAZARD_KEYWORDS  = {"dodge", "avoid", "trap", "spike", "hazard", "obstacle",
                     "danger", "mine", "pit", "lava", "poison"}

# ── Classes ───────────────────────────────────────────────────────────────────

CLASSES = ["Easy", "Medium", "Hard"]


# ── Feature extraction ────────────────────────────────────────────────────────

def _extract_features(design_doc: dict) -> list[float]:
    """
    Convert a design document into a 5-element feature vector.

    Returns: [mechanic_count, entity_count, has_boss, has_upgrades, has_hazards]
    """
    mechanics   = [m.lower() for m in (design_doc.get("mechanics") or [])]
    entities    = design_doc.get("entities") or []
    description = (design_doc.get("description") or design_doc.get("summary") or "").lower()

    all_text = description + " " + " ".join(mechanics)

    mechanic_count = min(len(mechanics), 10) / 10.0
    entity_count   = min(len(entities),  12) / 12.0

    has_boss     = float(any(kw in all_text for kw in _BOSS_KEYWORDS))
    has_upgrades = float(any(kw in all_text for kw in _UPGRADE_KEYWORDS))
    has_hazards  = float(any(kw in all_text for kw in _HAZARD_KEYWORDS))

    return [mechanic_count, entity_count, has_boss, has_upgrades, has_hazards]


FEATURE_NAMES = ["mechanic_count", "entity_count", "has_boss", "has_upgrades", "has_hazards"]


# ── Perceptron (from scratch) ─────────────────────────────────────────────────

class MultiClassPerceptron:
    """
    Multi-class Perceptron using One-vs-Rest strategy.

    Maintains one weight vector per class.
    Prediction = class whose weight vector scores highest on the input.
    """

    def __init__(self, n_features: int, classes: list[str], learning_rate: float = 0.1):
        self.classes       = classes
        self.learning_rate = learning_rate
        self.n_features    = n_features

        # Weight vector for each class: weights[class_index][feature_index]
        # Initialized to small random values to break symmetry
        random.seed(42)
        self.weights: list[list[float]] = [
            [random.uniform(-0.1, 0.1) for _ in range(n_features)]
            for _ in classes
        ]
        # Bias term for each class
        self.biases: list[float] = [0.0 for _ in classes]

    def _dot(self, weights: list[float], features: list[float]) -> float:
        """Dot product: sum of weight * feature for each dimension."""
        return sum(w * f for w, f in zip(weights, features))

    def _score(self, features: list[float]) -> list[float]:
        """Compute raw score for each class."""
        return [
            self._dot(self.weights[i], features) + self.biases[i]
            for i in range(len(self.classes))
        ]

    def predict(self, features: list[float]) -> str:
        """Return the class with the highest score."""
        scores = self._score(features)
        best_idx = scores.index(max(scores))
        return self.classes[best_idx]

    def predict_with_scores(self, features: list[float]) -> tuple[str, dict[str, float]]:
        """Return prediction + raw scores per class."""
        scores   = self._score(features)
        scores_d = {c: round(scores[i], 4) for i, c in enumerate(self.classes)}
        best     = max(scores_d, key=scores_d.__getitem__)
        return best, scores_d

    def train(self, X: list[list[float]], y: list[str], epochs: int = 100) -> list[float]:
        """
        Train using the perceptron learning rule.

        For each misclassified example:
          correct_class_weights  += learning_rate * features
          predicted_class_weights -= learning_rate * features

        Returns loss history (fraction of mistakes per epoch).
        """
        loss_history = []

        for epoch in range(epochs):
            mistakes = 0
            # Shuffle training data each epoch — seeded per epoch for determinism
            indices = list(range(len(X)))
            random.seed(42 + epoch)
            random.shuffle(indices)

            for idx in indices:
                features      = X[idx]
                true_label    = y[idx]
                predicted     = self.predict(features)

                if predicted != true_label:
                    mistakes += 1
                    true_idx = self.classes.index(true_label)
                    pred_idx = self.classes.index(predicted)

                    # Reward correct class: push weights toward this example
                    for j in range(self.n_features):
                        self.weights[true_idx][j] += self.learning_rate * features[j]
                    self.biases[true_idx] += self.learning_rate

                    # Penalize predicted class: push weights away from this example
                    for j in range(self.n_features):
                        self.weights[pred_idx][j] -= self.learning_rate * features[j]
                    self.biases[pred_idx] -= self.learning_rate

            loss = mistakes / len(X)
            loss_history.append(loss)

            # Early stop if perfect
            if mistakes == 0:
                logger.debug("Perceptron converged at epoch %d", epoch + 1)
                break

        return loss_history

    def accuracy(self, X: list[list[float]], y: list[str]) -> float:
        correct = sum(1 for features, label in zip(X, y) if self.predict(features) == label)
        return correct / len(X)


# ── Training data ─────────────────────────────────────────────────────────────
# Format: (design_doc, label)

def _doc(mechanics, entities, description=""):
    return {"mechanics": mechanics, "entities": entities, "description": description}


_TRAINING_DATA = [
    # ── Easy ──────────────────────────────────────────────────────────────────
    (_doc(["tap to fly", "gravity"],
          ["Bird", "Pipe"],
          "tap to fly avoid pipes simple score"), "Easy"),

    (_doc(["eat food", "grow longer", "avoid walls"],
          ["Snake", "Food"],
          "basic snake game eat food grow avoid walls"), "Easy"),

    (_doc(["jump", "run"],
          ["Player", "Platform"],
          "simple jump platformer no enemies"), "Easy"),

    (_doc(["click to score"],
          ["Button", "Score"],
          "idle clicker tap button increase score"), "Easy"),

    (_doc(["tap to fly", "avoid obstacles", "gravity", "score counter"],
          ["Bird", "Pipe", "Ground"],
          "flappy clone very simple tap and fly"), "Easy"),

    (_doc(["move left right", "collect coins"],
          ["Player", "Coin", "Platform"],
          "collect coins no enemies simple movement"), "Easy"),

    (_doc(["shoot", "score"],
          ["Player", "Target"],
          "basic shooting gallery hit targets for score"), "Easy"),

    (_doc(["match colors"],
          ["Block", "Board"],
          "simple match 3 no timer no hazards"), "Easy"),

    (_doc(["drive", "stay on road"],
          ["Car", "Road"],
          "basic driving stay on road no traffic"), "Easy"),

    (_doc(["jump over obstacles"],
          ["Player", "Obstacle"],
          "endless runner jump over simple obstacles"), "Easy"),

    # ── Medium ────────────────────────────────────────────────────────────────
    (_doc(["jump", "run", "collect coins", "avoid enemies"],
          ["Player", "Enemy", "Coin", "Platform"],
          "platformer jump collect coins avoid enemies"), "Medium"),

    (_doc(["place towers", "upgrade towers", "wave enemies", "gold economy"],
          ["Tower", "Enemy", "Gold", "Base", "Wave"],
          "tower defense place upgrade towers stop waves"), "Medium"),

    (_doc(["match 3", "timer", "chain reactions", "power ups"],
          ["Block", "Board", "Timer", "PowerUp"],
          "match 3 puzzle with timer chain reactions and power ups"), "Medium"),

    (_doc(["shoot", "dodge", "score multiplier"],
          ["Player", "Enemy", "Bullet", "Score"],
          "side scroller shoot enemies dodge bullets"), "Medium"),

    (_doc(["eat food", "grow longer", "avoid walls", "speed increase", "power-ups"],
          ["Snake", "Food", "PowerUp", "Wall"],
          "snake with speed increase and power ups"), "Medium"),

    (_doc(["jump", "wall jump", "collect", "avoid spikes"],
          ["Player", "Platform", "Spike", "Coin"],
          "platformer wall jump avoid spike traps collect coins"), "Medium"),

    (_doc(["accelerate", "drift", "avoid traffic", "lap timer"],
          ["Car", "Traffic", "Track", "Timer"],
          "racing game avoid traffic drift around corners lap timer"), "Medium"),

    (_doc(["tap on beat", "note highway", "combo multiplier", "timing accuracy"],
          ["Note", "Highway", "Beat", "Score", "Combo"],
          "rhythm game tap notes build combo multiplier"), "Medium"),

    (_doc(["shoot", "dodge enemies", "power-ups", "wave system"],
          ["Ship", "Alien", "PowerUp", "Laser"],
          "space shooter wave system dodge power ups no boss"), "Medium"),

    (_doc(["level up", "collect loot", "quest system"],
          ["Hero", "Enemy", "NPC", "Chest"],
          "simple rpg level up collect loot quests no boss fight"), "Medium"),

    # ── Hard ──────────────────────────────────────────────────────────────────
    (_doc(["shoot bullets", "dodge enemies", "power-ups", "boss fights", "weapon upgrades"],
          ["Ship", "Alien", "Boss", "Asteroid", "PowerUp", "Laser"],
          "space shooter with boss fights weapon upgrades dodge hazards"), "Hard"),

    (_doc(["survive waves", "upgrade weapons", "collect ammo", "craft", "boss fight"],
          ["Player", "Zombie", "Boss", "AmmoBox", "Weapon", "Barricade"],
          "zombie survival crafting weapon upgrades boss enemies dodge traps"), "Hard"),

    (_doc(["level up", "collect loot", "quest system", "boss fight", "skill tree"],
          ["Hero", "Enemy", "Boss", "NPC", "Chest", "Spell", "Weapon"],
          "dungeon rpg level up skill tree loot system boss fight dodge traps"), "Hard"),

    (_doc(["punch", "kick", "combo", "block", "special attack", "parry"],
          ["Player", "Enemy", "Boss", "Arena", "Health"],
          "fighting game combos special moves boss battle dodge attacks"), "Hard"),

    (_doc(["double jump", "wall jump", "collect coins", "boss fight", "upgrade"],
          ["Player", "Enemy", "Boss", "Coin", "Platform", "Checkpoint"],
          "platformer double jump wall jump boss fights upgrades spike hazards"), "Hard"),

    (_doc(["shoot", "dash", "dodge", "upgrade", "boss fight"],
          ["Player", "Enemy", "Boss", "PowerUp", "Weapon"],
          "twin stick shooter boss fights weapon upgrades dodge hazards"), "Hard"),

    (_doc(["shoot", "dodge bullets", "weapon upgrades", "score multiplier", "boss"],
          ["Player", "Enemy", "Boss", "Bullet", "PowerUp", "Shield"],
          "bullet hell shooter weapon upgrades boss stages dodge avoid"), "Hard"),

    (_doc(["drift", "boost", "turbo", "lap timer", "upgrade car", "avoid obstacles"],
          ["Car", "Opponent", "Track", "Boost", "Obstacle", "Finish"],
          "racing drift turbo car upgrades obstacles avoid hazards"), "Hard"),

    (_doc(["explore", "shoot", "loot", "upgrade", "boss fight", "craft"],
          ["Player", "Enemy", "Boss", "Chest", "Weapon", "Map", "NPC"],
          "open world shooter loot crafting boss fights dodge traps"), "Hard"),

    (_doc(["survive", "upgrade", "defend", "boss", "dodge waves"],
          ["Player", "Enemy", "Boss", "Resource", "Tower", "Wall"],
          "base defense survival upgrade towers boss fight dodge enemy waves"), "Hard"),
]


# ── Model lifecycle ───────────────────────────────────────────────────────────

_perceptron: MultiClassPerceptron | None = None


def _train() -> MultiClassPerceptron:
    X = [_extract_features(doc) for doc, _ in _TRAINING_DATA]
    y = [label for _, label in _TRAINING_DATA]

    model = MultiClassPerceptron(
        n_features=len(FEATURE_NAMES),
        classes=CLASSES,
        learning_rate=0.1,
    )
    loss_history = model.train(X, y, epochs=200)
    acc = model.accuracy(X, y)
    logger.info(
        "Difficulty perceptron trained — accuracy=%.0f%% final_loss=%.2f",
        acc * 100, loss_history[-1],
    )
    return model


def _get_model() -> MultiClassPerceptron:
    global _perceptron
    if _perceptron is None:
        _perceptron = _train()
    return _perceptron


# ── Public API ────────────────────────────────────────────────────────────────

def predict_difficulty(design_doc: dict) -> dict[str, Any]:
    """
    Predict the difficulty of a game from its design document.

    Returns
    -------
    {
        "difficulty":   "Hard",
        "scores":       {"Easy": -1.23, "Medium": 0.45, "Hard": 2.10},
        "features":     {"mechanic_count": 0.7, "has_boss": 1.0, ...},
        "explanation":  "This game has a boss fight, upgrades, and hazards."
    }
    """
    model    = _get_model()
    features = _extract_features(design_doc)

    difficulty, scores = model.predict_with_scores(features)

    # Human-readable explanation
    reasons = []
    if features[2] == 1.0:
        reasons.append("has a boss fight")
    if features[3] == 1.0:
        reasons.append("has upgrades/progression")
    if features[4] == 1.0:
        reasons.append("has hazards to dodge")
    if features[0] >= 0.5:
        reasons.append(f"has {int(features[0]*10)}+ mechanics")
    if features[1] >= 0.5:
        reasons.append(f"has {int(features[1]*12)}+ entities")

    if not reasons:
        explanation = "Simple mechanics and few entities make this easy to play."
    else:
        explanation = "This game is challenging because it " + ", ".join(reasons) + "."

    return {
        "difficulty":  difficulty,
        "scores":      scores,
        "features":    {name: round(val, 3) for name, val in zip(FEATURE_NAMES, features)},
        "explanation": explanation,
    }
