"""
Game Success Predictor
======================
Algorithm : Feature engineering + Random Forest Classifier
Task      : Multi-class classification — predict popularity tier
Classes   : High | Medium | Low  (based on expected plays)

How it works
------------
1. Structured features are extracted from the game design document:
     - game_type_encoded   : label-encoded game type (ordinal by avg popularity)
     - mechanic_count      : number of mechanics in the design
     - entity_count        : number of entities generated
     - description_length  : word count of the description
     - has_boss            : boss fight mechanic present (0/1)
     - has_upgrades        : upgrade/level-up mechanic present (0/1)
     - has_multiplayer     : co-op or multiplayer present (0/1)
     - visual_richness     : number of visual style fields specified
     - mechanic_diversity  : fraction of unique mechanic categories covered

2. Random Forest Classifier (100 estimators) predicts the tier.
   Random Forest was chosen because:
     - Ensemble of decision trees → naturally handles mixed feature types
     - Built-in feature importance → shows WHICH features drive popularity
     - Robust to small training sets (bagging reduces variance)
     - Non-linear boundaries capture interactions (e.g. boss + upgrades
       together predict High better than either alone)

3. Feature importance is exposed for demo / explanation purposes.

Training data
-------------
Synthetic training examples derived from the seed game catalogue,
reflecting real patterns:
  - Space shooters with boss fights → typically High
  - Simple arcade games, minimal mechanics → typically Low
  - RPGs with upgrades + loot → High
  - Flappy-style games → Medium–Low

Integration
-----------
Called from ai_orchestrator.generate_design() after the design doc is
produced.  Returns tier + confidence + feature importance so the frontend
can show "Predicted Popularity: High 🎯" with an explanation.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
MODEL_PATH = BASE_DIR / "models" / "success_predictor.pkl"

_model:   RandomForestClassifier | None = None
_encoder: LabelEncoder | None           = None

# ── Game type popularity ordering (from seed data averages) ──────────────────
# Higher rank = more popular on average
_GAME_TYPE_RANK: dict[str, int] = {
    "topdown":       15,
    "fighting":      14,
    "shooter":       13,
    "space_shooter": 12,
    "survival":      11,
    "rpg":           10,
    "platformer":     9,
    "racing":         8,
    "puzzle":         7,
    "tower_defense":  6,
    "arcade":         5,
    "clicker":        4,
    "simulation":     4,
    "sports":         3,
    "rhythm":         3,
    "flappy":         2,
    "snake":          2,
}

_BOSS_KEYWORDS    = {"boss", "final boss", "boss fight", "boss battle"}
_UPGRADE_KEYWORDS = {"upgrade", "level up", "level-up", "skill tree", "upgrade shop",
                     "power up", "powerup", "prestige", "evolve"}
_MULTI_KEYWORDS   = {"multiplayer", "co-op", "coop", "2 player", "two player", "pvp"}
_VISUAL_FIELDS    = {"theme", "primary_colors", "background"}


def _extract_features(design_doc: dict) -> list[float]:
    """Extract feature vector from a design document."""
    game_type   = (design_doc.get("game_type") or "arcade").lower()
    mechanics   = [m.lower() for m in (design_doc.get("mechanics") or [])]
    entities    = design_doc.get("entities") or []
    description = (design_doc.get("description") or design_doc.get("summary") or "").lower()
    visual      = design_doc.get("visual_style") or {}

    # Game type rank (normalised 0–1)
    gt_rank = _GAME_TYPE_RANK.get(game_type, 5) / 15.0

    # Mechanic count (normalised, cap at 10)
    mechanic_count = min(len(mechanics), 10) / 10.0

    # Entity count (normalised, cap at 12)
    entity_count = min(len(entities), 12) / 12.0

    # Description length (word count, cap at 60)
    desc_words = len(description.split())
    desc_len   = min(desc_words, 60) / 60.0

    # Boss mechanic present
    has_boss = float(
        any(kw in description for kw in _BOSS_KEYWORDS) or
        any(kw in m for kw in _BOSS_KEYWORDS for m in mechanics)
    )

    # Upgrade mechanic present
    has_upgrades = float(
        any(kw in description for kw in _UPGRADE_KEYWORDS) or
        any(kw in m for kw in _UPGRADE_KEYWORDS for m in mechanics)
    )

    # Multiplayer
    has_multi = float(any(kw in description for kw in _MULTI_KEYWORDS))

    # Visual richness (how many visual style fields are filled)
    visual_richness = sum(1 for f in _VISUAL_FIELDS if visual.get(f)) / len(_VISUAL_FIELDS)

    # Mechanic diversity: fraction of broad categories covered
    categories = {
        "movement": {"jump", "run", "dash", "fly", "swim", "climb", "glide"},
        "combat":   {"shoot", "fight", "attack", "punch", "kick", "combo"},
        "collect":  {"collect", "loot", "pick up", "gather", "mine"},
        "progress": {"upgrade", "level up", "evolve", "prestige", "skill"},
        "hazard":   {"dodge", "avoid", "survive", "defend", "block"},
    }
    covered = sum(
        1 for cat_words in categories.values()
        if any(any(cw in m for cw in cat_words) for m in mechanics)
    ) / len(categories)

    return [
        gt_rank, mechanic_count, entity_count, desc_len,
        has_boss, has_upgrades, has_multi, visual_richness, covered,
    ]


FEATURE_NAMES = [
    "game_type_popularity", "mechanic_count", "entity_count", "description_length",
    "has_boss", "has_upgrades", "has_multiplayer", "visual_richness", "mechanic_diversity",
]

# ── Training data ─────────────────────────────────────────────────────────────
# Format: (design_doc_dict, label)  label: "High" | "Medium" | "Low"

def _make_doc(game_type, mechanics, entities, description, visual=None, has_boss=False, has_upgrades=False):
    return {
        "game_type":   game_type,
        "mechanics":   mechanics,
        "entities":    entities,
        "description": description,
        "visual_style": visual or {},
    }


_TRAINING_DATA = [
    # ── High popularity ───────────────────────────────────────────────────
    (_make_doc("topdown",       ["shoot", "dash", "dodge", "upgrade", "boss fight"],
               ["Player","Enemy","Boss","PowerUp","Weapon"],
               "twin stick top down shooter with boss fights weapon upgrades and arena combat",
               {"theme":"neon","primary_colors":["#ff00ff"],"background":"#000"}), "High"),

    (_make_doc("fighting",      ["punch","kick","combo","block","special attack","parry"],
               ["Player","Enemy","Boss","Arena","Health"],
               "2d fighting game with combos special moves and boss battles",
               {"theme":"pixel","primary_colors":["#ff0000"],"background":"#111"}), "High"),

    (_make_doc("space_shooter", ["shoot bullets","dodge enemies","power-ups","boss fights","weapon upgrades"],
               ["Ship","Alien","Boss","Asteroid","PowerUp","Laser"],
               "space shooter defending earth from alien invasion with upgrades and boss levels",
               {"theme":"dark","primary_colors":["#00ffff"],"background":"#000020"}), "High"),

    (_make_doc("survival",      ["survive waves","upgrade weapons","collect ammo","craft","boss fight"],
               ["Player","Zombie","Boss","AmmoBox","Weapon","Barricade"],
               "zombie survival game with crafting weapon upgrades and boss enemies",
               {"theme":"dark","primary_colors":["#33cc33"],"background":"#1a1a1a"}), "High"),

    (_make_doc("rpg",           ["level up","collect loot","quest system","boss fight","skill tree"],
               ["Hero","Enemy","Boss","NPC","Chest","Spell","Weapon"],
               "dungeon rpg with level up skill tree loot system and dragon boss",
               {"theme":"fantasy","primary_colors":["#gold"],"background":"#2d1b00"}), "High"),

    (_make_doc("shooter",       ["shoot","dodge bullets","weapon upgrades","score multiplier","boss"],
               ["Player","Enemy","Boss","Bullet","PowerUp","Shield"],
               "bullet hell shooter with weapon upgrades score multiplier and boss stages",
               {"theme":"retro","primary_colors":["#ff6600"],"background":"#000"}), "High"),

    (_make_doc("platformer",    ["double jump","wall jump","collect coins","boss fight","upgrade"],
               ["Player","Enemy","Boss","Coin","Platform","Checkpoint"],
               "pixel platformer with double jump wall jump boss fights and upgrades",
               {"theme":"pixel","primary_colors":["#ffcc00"],"background":"#87ceeb"}), "High"),

    (_make_doc("racing",        ["drift","boost","turbo","lap timer","upgrade car"],
               ["Car","Opponent","Track","Boost","Obstacle","Finish"],
               "racing game with drift mechanics turbo boost car upgrades and lap timer",
               {"theme":"neon","primary_colors":["#ff0080"],"background":"#111"}), "High"),

    (_make_doc("topdown",       ["explore","shoot","loot","upgrade","boss fight","craft"],
               ["Player","Enemy","Boss","Chest","Weapon","Map","NPC"],
               "open world topdown shooter with loot crafting and boss fights",
               {"theme":"dark","primary_colors":["#00cc99"],"background":"#0d1117"}), "High"),

    (_make_doc("survival",      ["collect","survive","upgrade","defend","boss"],
               ["Player","Enemy","Boss","Resource","Tower","Wall"],
               "base building survival game defend against waves upgrade towers boss fight",
               {"theme":"post-apocalyptic","primary_colors":["#cc6600"],"background":"#2b1d0e"}), "High"),

    # ── Medium popularity ─────────────────────────────────────────────────
    (_make_doc("platformer",    ["jump","run","collect coins","avoid enemies"],
               ["Player","Enemy","Coin","Platform"],
               "classic platformer jump and collect coins avoid enemies",
               {"theme":"pixel","primary_colors":["#ff9900"],"background":"#87ceeb"}), "Medium"),

    (_make_doc("puzzle",        ["match colors","clear lines","timer","chain reactions"],
               ["Block","Board","Timer","Score"],
               "match 3 puzzle game with timer and chain reactions",
               {"theme":"colorful","primary_colors":["#ff00ff"],"background":"#fff"}), "Medium"),

    (_make_doc("tower_defense", ["place towers","upgrade towers","wave enemies","gold economy"],
               ["Tower","Enemy","Gold","Base","Wave"],
               "tower defense place and upgrade towers stop enemy waves",
               {"theme":"fantasy","primary_colors":["#009900"],"background":"#336633"}), "Medium"),

    (_make_doc("arcade",        ["high score","increasing difficulty","lives system","dodge"],
               ["Player","Obstacle","Score","Life"],
               "endless arcade game dodge obstacles high score increasing difficulty",
               {"theme":"retro","primary_colors":["#ff6600"],"background":"#000"}), "Medium"),

    (_make_doc("rpg",           ["level up","collect loot","quest system"],
               ["Hero","Enemy","NPC","Chest"],
               "simple rpg with level up and loot no boss",
               {}), "Medium"),

    (_make_doc("snake",         ["eat food","grow longer","avoid walls","speed increase","power-ups"],
               ["Snake","Food","PowerUp","Wall"],
               "snake game with power ups and increasing speed",
               {"theme":"neon","primary_colors":["#00ff00"],"background":"#000"}), "Medium"),

    (_make_doc("racing",        ["accelerate","drift","avoid traffic","lap timer"],
               ["Car","Traffic","Track","Timer"],
               "top down racing game avoid traffic drift around corners",
               {}), "Medium"),

    (_make_doc("clicker",       ["click to earn","buy upgrades","passive income","prestige"],
               ["Cookie","Upgrade","Worker","Prestige"],
               "idle clicker game buy upgrades passive income prestige system",
               {"theme":"colorful","primary_colors":["#cc8800"],"background":"#fff9f0"}), "Medium"),

    (_make_doc("shooter",       ["shoot","dodge","score multiplier"],
               ["Player","Enemy","Bullet","Score"],
               "side scrolling shooter shoot enemies dodge bullets score",
               {"theme":"retro","primary_colors":["#ff0000"],"background":"#000"}), "Medium"),

    (_make_doc("rhythm",        ["tap on beat","note highway","combo multiplier","timing accuracy"],
               ["Note","Highway","Beat","Score","Combo"],
               "rhythm game tap notes on beat build combo multiplier",
               {"theme":"neon","primary_colors":["#ff00cc"],"background":"#0a0a0a"}), "Medium"),

    # ── Low popularity ────────────────────────────────────────────────────
    (_make_doc("flappy",        ["tap to fly","avoid pipes","gravity"],
               ["Bird","Pipe","Score"],
               "tap to fly avoid pipes score counter",
               {}), "Low"),

    (_make_doc("snake",         ["eat food","grow longer","avoid walls"],
               ["Snake","Food"],
               "basic snake game eat food grow longer avoid walls",
               {}), "Low"),

    (_make_doc("arcade",        ["high score","simple controls"],
               ["Player","Score"],
               "simple arcade game high score",
               {}), "Low"),

    (_make_doc("flappy",        ["tap to fly","avoid obstacles","gravity","score counter"],
               ["Bird","Pipe","Ground"],
               "flappy bird clone tap and fly basic game",
               {}), "Low"),

    (_make_doc("puzzle",        ["match colors","timer"],
               ["Block","Timer"],
               "simple match puzzle timer",
               {}), "Low"),

    (_make_doc("simulation",    ["manage resources","produce goods"],
               ["Farm","Crop","Worker"],
               "basic farm simulation grow crops",
               {}), "Low"),

    (_make_doc("sports",        ["score goals","timer"],
               ["Ball","Player","Goal"],
               "simple sports game score goals timer",
               {}), "Low"),

    (_make_doc("arcade",        ["increasing difficulty","simple controls","lives"],
               ["Player","Obstacle","Life"],
               "endless runner dodge obstacles",
               {}), "Low"),

    (_make_doc("simulation",    ["time management","serve customers"],
               ["Customer","Item","Counter"],
               "basic cafe management serve customers",
               {}), "Low"),

    (_make_doc("flappy",        ["gravity","tap to fly"],
               ["Bird"],
               "fly through gaps avoid walls",
               {}), "Low"),
]


# ── Model lifecycle ───────────────────────────────────────────────────────────

def _train():
    X = np.array([_extract_features(doc) for doc, _ in _TRAINING_DATA])
    y = [label for _, label in _TRAINING_DATA]

    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        min_samples_leaf=2,
        random_state=42,
    )
    model.fit(X, y)
    return model


def _load_or_train() -> RandomForestClassifier:
    global _model
    if _model is not None:
        return _model

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as f:
                _model = pickle.load(f)
            logger.info("Success predictor loaded from %s", MODEL_PATH)
            return _model
        except Exception as exc:
            logger.warning("Could not load success predictor, retraining: %s", exc)

    _model = _train()
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(_model, f)
    logger.info("Success predictor trained and saved to %s", MODEL_PATH)
    return _model


# ── Public API ────────────────────────────────────────────────────────────────

def predict_success(design_doc: dict) -> dict[str, Any]:
    """
    Predict the popularity tier of a game from its design document.

    Returns
    -------
    {
        "tier":             "High",
        "confidence":       0.74,
        "probabilities":    {"High": 0.74, "Medium": 0.18, "Low": 0.08},
        "top_features":     [{"feature": "has_boss", "importance": 0.21}, ...],
        "tip":              "Adding boss fights and upgrades boosts predicted popularity."
    }
    """
    model    = _load_or_train()
    features = _extract_features(design_doc)
    X        = np.array([features])

    proba   = model.predict_proba(X)[0]
    classes = model.classes_
    probs   = {c: round(float(p), 3) for c, p in zip(classes, proba)}
    tier    = max(probs, key=probs.__getitem__)

    # Feature importance (global, from the forest)
    importances = model.feature_importances_
    top_features = sorted(
        [{"feature": n, "importance": round(float(v), 3)}
         for n, v in zip(FEATURE_NAMES, importances)],
        key=lambda x: x["importance"],
        reverse=True,
    )[:4]

    # Actionable tip
    f = features
    tips = []
    if f[4] == 0:   # no boss
        tips.append("add a boss fight")
    if f[5] == 0:   # no upgrades
        tips.append("include upgrades or progression")
    if f[1] < 0.4:  # few mechanics
        tips.append("add more mechanics (dash, combo, crafting)")
    if f[7] < 0.33: # low visual richness
        tips.append("specify a visual style")

    tip = ("Looks great — keep the mechanics rich!" if not tips
           else "To boost predicted popularity: " + ", ".join(tips[:2]) + ".")

    return {
        "tier":          tier,
        "confidence":    probs[tier],
        "probabilities": probs,
        "top_features":  top_features,
        "tip":           tip,
    }
