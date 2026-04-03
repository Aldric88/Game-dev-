"""
Prompt Quality Scorer
=====================
Algorithm : Feature engineering + Ridge Regression
Task      : Regression — score a game description prompt from 0 to 100

How it works
------------
1. Hand-engineered features are extracted from the raw prompt text:
     - has_game_type      : known game genre detected (0/1)
     - mechanic_count     : number of mechanic keywords found (0–8)
     - has_visual_style   : colour / art style keywords found (0/1)
     - word_count         : total words (normalised 0–1 over 0–80)
     - entity_count       : entity keywords found (0–6)
     - has_win_condition  : win/lose condition words found (0/1)
     - has_setting        : location / world keywords found (0/1)
     - specificity_ratio  : specific/descriptive words ÷ total words
     - sentence_count     : number of sentences (normalised)

2. Ridge Regression maps those 9 features to a score in [0, 100].
   Ridge (L2-regularised linear regression) was chosen because:
     - Feature set is small and well-understood
     - Prevents overfitting on the small synthetic training set
     - Score is smooth and interpretable

3. The model is trained on synthetic (prompt, score) pairs where
   scores were assigned by the rule that:
     - Vague prompts ("make a game")              → 10–25
     - Partially specified ("a platformer game")  → 30–55
     - Well-specified (genre + mechanics + style) → 60–80
     - Fully detailed (all signals present)       → 85–95

Training data
-------------
Synthetic pairs baked into this file.  The model can be retrained
with real MAPL reward data: high-reward prompts → high score.

Integration
-----------
Called from the /ai/design endpoint and from the lightweight
/ai/score-prompt endpoint (no credit cost) for real-time UI feedback.
"""

from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import MinMaxScaler
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
MODEL_PATH = BASE_DIR / "models" / "prompt_scorer.pkl"

_pipeline: Pipeline | None = None

# ── Keyword dictionaries ──────────────────────────────────────────────────────

_GAME_TYPE_WORDS = {
    "platformer", "shooter", "rpg", "puzzle", "arcade", "racing", "flappy",
    "snake", "space", "fighting", "survival", "topdown", "tower defense",
    "rhythm", "sports", "simulation", "clicker", "idle", "runner", "brawler",
    "adventure", "dungeon", "roguelike", "strategy",
}

_MECHANIC_WORDS = {
    "jump", "shoot", "collect", "dodge", "fight", "race", "build", "grow",
    "survive", "dash", "fly", "swim", "climb", "attack", "defend", "upgrade",
    "craft", "explore", "run", "bounce", "slide", "glide", "teleport",
    "combo", "charge", "block", "parry", "sneak", "hack",
}

_VISUAL_WORDS = {
    "neon", "pixel", "retro", "minimalist", "colorful", "dark", "bright",
    "cartoon", "realistic", "top-down", "side-scrolling", "isometric",
    "8-bit", "16-bit", "monochrome", "pastel", "gothic", "futuristic",
    "medieval", "cyberpunk", "fantasy", "sci-fi",
}

_ENTITY_WORDS = {
    "player", "enemy", "boss", "obstacle", "coin", "power-up", "powerup",
    "wall", "platform", "bullet", "weapon", "item", "npc", "ally", "trap",
    "projectile", "chest", "key", "door", "portal", "spike", "turret",
}

_WIN_WORDS = {
    "win", "lose", "score", "survive", "defeat", "collect", "reach",
    "escape", "complete", "finish", "kill", "destroy", "save", "protect",
    "goal", "objective", "mission",
}

_SETTING_WORDS = {
    "forest", "space", "city", "dungeon", "desert", "ocean", "sky", "cave",
    "castle", "jungle", "ice", "volcano", "mountain", "underground", "rooftop",
    "arena", "stadium", "lab", "ship", "planet",
}

_SPECIFIC_WORDS = (
    _MECHANIC_WORDS | _VISUAL_WORDS | _ENTITY_WORDS |
    _WIN_WORDS | _SETTING_WORDS | _GAME_TYPE_WORDS
)


def _extract_features(prompt: str) -> list[float]:
    """Convert a prompt string into a 9-element feature vector."""
    text  = prompt.lower()
    words = re.findall(r"[a-z0-9]+", text)
    wc    = max(len(words), 1)

    has_game_type     = float(any(w in _GAME_TYPE_WORDS for w in words) or
                              any(phrase in text for phrase in ["tower defense", "top-down"]))
    mechanic_count    = min(sum(1 for w in words if w in _MECHANIC_WORDS), 8) / 8.0
    has_visual_style  = float(any(w in _VISUAL_WORDS for w in words))
    word_count_norm   = min(wc, 80) / 80.0
    entity_count      = min(sum(1 for w in words if w in _ENTITY_WORDS), 6) / 6.0
    has_win_condition = float(any(w in _WIN_WORDS for w in words))
    has_setting       = float(any(w in _SETTING_WORDS for w in words))
    specificity_ratio = sum(1 for w in words if w in _SPECIFIC_WORDS) / wc
    sentence_count    = min(len(re.split(r"[.!?,;]", prompt)), 5) / 5.0

    return [
        has_game_type,
        mechanic_count,
        has_visual_style,
        word_count_norm,
        entity_count,
        has_win_condition,
        has_setting,
        specificity_ratio,
        sentence_count,
    ]


# ── Training data ─────────────────────────────────────────────────────────────

_TRAINING_DATA: list[tuple[str, float]] = [
    # Very vague (10–25)
    ("make a game",                                                                      12),
    ("game",                                                                             8),
    ("a fun game",                                                                       15),
    ("create something cool",                                                            14),
    ("make a game with a player",                                                        20),
    ("i want a game",                                                                    11),
    ("build a game for me",                                                              18),
    ("a simple game",                                                                    16),
    ("game with enemies",                                                                22),
    ("something with shooting",                                                          20),

    # Partially specified (30–55)
    ("a platformer game",                                                                33),
    ("make a space shooter",                                                             38),
    ("a puzzle game with blocks",                                                        40),
    ("runner game where you dodge obstacles",                                            44),
    ("a game where you collect coins",                                                   42),
    ("pixel art platformer with enemies",                                                52),
    ("top down shooter with power ups",                                                  48),
    ("survival game where you survive waves",                                            50),
    ("racing game with boost and drifting",                                              54),
    ("retro arcade game with high score",                                                49),
    ("a snake game with power ups and levels",                                           46),
    ("rpg game with a hero who levels up",                                               51),
    ("flappy bird style game",                                                           36),
    ("tower defense with different enemy types",                                         53),
    ("a fighting game with combos",                                                      47),

    # Well specified (60–80)
    ("a pixel art platformer where the player jumps and collects coins while dodging enemies", 65),
    ("space shooter game where you defend earth from alien waves with power up weapons",  68),
    ("retro dungeon rpg where the player explores caves collects loot and fights bosses", 72),
    ("neon arcade game with increasing difficulty where you dodge bullets and collect stars", 70),
    ("top down survival game in a forest where you craft weapons and survive zombie waves", 75),
    ("colorful puzzle game where you match blocks to clear lines before the timer runs out", 67),
    ("pixel racing game with drift mechanics turbo boost and lap timer on a city track",  74),
    ("dark gothic tower defense where you place archers and cannons to stop skeleton armies", 78),
    ("rhythm game where you tap falling notes in time with music to build combos",        71),
    ("side scrolling brawler in a jungle where you punch enemies and collect health packs", 69),
    ("futuristic snake game in a neon arena with power ups speed increase and growing snake", 73),
    ("cartoon platformer with double jump wall jump and checkpoints in a sky world",      76),

    # Fully detailed (85–95)
    (
        "create a pixel art platformer with a hero who can double jump and wall jump. "
        "The player collects coins and defeats slime enemies. There is a boss at the end "
        "of each level. Visual style is retro 8-bit with a forest theme.",
        88,
    ),
    (
        "make a neon cyberpunk top down shooter where the player dashes and shoots lasers. "
        "Enemies come in waves and drop power ups. The player upgrades weapons between levels. "
        "Win by surviving all waves and defeating the final boss.",
        91,
    ),
    (
        "build a retro space shooter where the player pilots a spaceship defending earth "
        "from alien invasion. Collect shield power ups and weapon upgrades. Game has 5 levels "
        "with increasing difficulty and a boss fight per level. Dark space background with neon ships.",
        90,
    ),
    (
        "a gothic dark dungeon rpg with turn based combat. The hero explores procedurally "
        "generated caves collecting weapons and armor. Level up system with skill tree. "
        "Final boss is a dragon king. Medieval pixel art visual style.",
        89,
    ),
    (
        "colorful cartoon kart racing game with drift mechanics and nitro boost. "
        "Player races against 3 AI opponents on 3 tracks. Collect power ups on track. "
        "Timer per lap and final position scoring. Win by finishing first in all races.",
        92,
    ),
    (
        "zombie survival game in a dark city. Player starts with a pistol and must survive "
        "30 waves of zombies. Collect ammo and craft weapons. Day night cycle changes enemy behavior. "
        "Upgrade station between waves. Lose when health reaches zero.",
        93,
    ),
]


# ── Model lifecycle ───────────────────────────────────────────────────────────

def _train() -> tuple:
    X = np.array([_extract_features(p) for p, _ in _TRAINING_DATA])
    y = np.array([s for _, s in _TRAINING_DATA], dtype=float)

    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=1.0)
    model.fit(X_scaled, y)
    return model, scaler


def _load_or_train():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as f:
                _pipeline = pickle.load(f)
            logger.info("Prompt scorer loaded from %s", MODEL_PATH)
            return _pipeline
        except Exception as exc:
            logger.warning("Could not load prompt scorer, retraining: %s", exc)

    model, scaler = _train()
    _pipeline = (model, scaler)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(_pipeline, f)
    logger.info("Prompt scorer trained and saved to %s", MODEL_PATH)
    return _pipeline


# ── Public API ────────────────────────────────────────────────────────────────

def score_prompt(prompt: str) -> dict[str, Any]:
    """
    Score a game description prompt from 0 to 100.

    Returns
    -------
    {
        "score":    72,
        "label":    "Good",
        "feedback": ["Add a visual style", "Mention win conditions"],
        "features": { ... }   # raw feature values for transparency
    }
    """
    model, scaler = _load_or_train()

    features     = _extract_features(prompt)
    X            = scaler.transform([features])
    raw_score    = float(model.predict(X)[0])
    score        = int(max(0, min(100, round(raw_score))))

    # Label
    if score >= 75:
        label = "Strong"
    elif score >= 50:
        label = "Good"
    elif score >= 30:
        label = "Fair"
    else:
        label = "Weak"

    # Actionable feedback
    feedback: list[str] = []
    f = features  # [game_type, mechanic, visual, word_count, entity, win, setting, spec, sentence]
    if f[0] == 0:
        feedback.append("Mention a game type (e.g. platformer, shooter, puzzle)")
    if f[1] < 0.25:
        feedback.append("Describe some mechanics (e.g. jump, shoot, collect)")
    if f[2] == 0:
        feedback.append("Add a visual style (e.g. pixel art, neon, retro)")
    if f[3] < 0.2:
        feedback.append("Add more detail to your description")
    if f[4] < 0.17:
        feedback.append("Name some game elements (player, enemy, boss, coins)")
    if f[5] == 0:
        feedback.append("Include a win or lose condition")
    if f[6] == 0:
        feedback.append("Describe the setting or world")

    return {
        "score":   score,
        "label":   label,
        "feedback": feedback[:3],   # top 3 most impactful suggestions
        "features": {
            "has_game_type":     bool(f[0]),
            "mechanic_count":    round(f[1] * 8),
            "has_visual_style":  bool(f[2]),
            "word_count":        round(f[3] * 80),
            "entity_count":      round(f[4] * 6),
            "has_win_condition": bool(f[5]),
            "has_setting":       bool(f[6]),
        },
    }
