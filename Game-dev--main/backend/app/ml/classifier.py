"""
Game Type Classifier — Runtime Inference
=========================================
Loads the trained model and exposes a single function:
    predict_game_type(prompt: str) -> dict

Drop-in replacement for the keyword matching in game_inference.py.

Example:
    from app.ml.classifier import predict_game_type

    result = predict_game_type("make a mario style game")
    # {
    #   "game_type": "platformer",
    #   "confidence": 0.94,
    #   "top3": [
    #       {"game_type": "platformer",    "confidence": 0.94},
    #       {"game_type": "arcade",        "confidence": 0.03},
    #       {"game_type": "topdown",       "confidence": 0.02},
    #   ]
    # }
"""

import re
import pickle
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.50   # single source of truth — imported by search_service

BASE_DIR   = Path(__file__).parent
MODEL_PATH = BASE_DIR / "models" / "game_type_classifier.pkl"

# Loaded once at startup, reused for every request
_pipeline = None


def _load_model():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    if not MODEL_PATH.exists():
        logger.warning(
            "Classifier model not found at %s. "
            "Run: python -m app.ml.train_classifier",
            MODEL_PATH
        )
        return None

    with open(MODEL_PATH, "rb") as f:
        _pipeline = pickle.load(f)

    logger.info("Game type classifier loaded from %s", MODEL_PATH)
    return _pipeline


def predict_game_type(prompt: str) -> dict:
    """
    Predict game type from a user prompt.

    Returns:
        {
            "game_type":        str,    # best prediction
            "confidence":       float,  # 0.0 – 1.0
            "needs_clarification": bool, # True when confidence < CONFIDENCE_THRESHOLD (0.50)
            "top3": [                   # top 3 predictions with scores
                {"game_type": str, "confidence": float},
                ...
            ],
            "source": "ml_model" | "keyword_fallback"
        }
    """
    pipeline = _load_model()

    # Model not trained yet — fall back to keyword matching
    if pipeline is None:
        return _keyword_fallback(prompt)

    try:
        predicted    = pipeline.predict([prompt])[0]
        probabilities = pipeline.predict_proba([prompt])[0]
        classes      = pipeline.classes_

        # Sort by confidence descending
        ranked = sorted(
            zip(classes, probabilities),
            key=lambda x: x[1],
            reverse=True
        )

        confidence = float(max(probabilities))

        # Short/vague prompts: fewer than 2 real words, or confidence below threshold
        # and the top prediction is "arcade" (the catch-all bucket).
        # These should always ask for clarification regardless of raw confidence.
        word_count = len(re.findall(r"[a-z]{2,}", prompt.lower()))
        is_vague = (
            confidence < CONFIDENCE_THRESHOLD
            or (word_count <= 1 and predicted == "arcade")
        )

        return {
            "game_type":           predicted,
            "confidence":          confidence,
            "needs_clarification": is_vague,
            "top3": [
                {"game_type": g, "confidence": round(float(c), 4)}
                for g, c in ranked[:3]
            ],
            "source": "ml_model"
        }

    except Exception as e:
        logger.error("Classifier prediction failed: %s", e)
        return _keyword_fallback(prompt)


def _keyword_fallback(prompt: str) -> dict:
    """
    Original keyword-based game type detection.
    Used when the ML model is not trained yet.
    Identical logic to game_inference.py._infer_game_type()
    """
    text = prompt.lower()

    if any(w in text for w in ["platform", "jump", "mario", "sonic", "side scroll"]):
        game_type = "platformer"
    elif any(w in text for w in ["flappy", "bird", "pipe", "tap to fly", "copter"]):
        game_type = "flappy"
    elif any(w in text for w in ["snake", "worm", "slither", "grow"]):
        game_type = "snake"
    elif any(w in text for w in ["space", "alien", "spaceship", "galaxy", "asteroid", "invader"]):
        game_type = "space_shooter"
    elif any(w in text for w in ["tower defense", "tower defence", "td game", "defend base", "plants vs"]):
        game_type = "tower_defense"
    elif any(w in text for w in ["fight", "punch", "combat", "beat em up", "street fighter", "brawl"]):
        game_type = "fighting"
    elif any(w in text for w in ["survival", "survive", "zombie", "horde", "wave", "vampire survivor"]):
        game_type = "survival"
    elif any(w in text for w in ["race", "racing", "car", "drive", "driving", "kart", "drift"]):
        game_type = "racing"
    elif any(w in text for w in ["puzzle", "match", "tetris", "block", "slide", "maze", "logic"]):
        game_type = "puzzle"
    elif any(w in text for w in ["rpg", "quest", "dungeon", "level up", "zelda", "pokemon", "adventure"]):
        game_type = "rpg"
    elif any(w in text for w in ["top down", "overhead", "birds eye", "topdown", "gta"]):
        game_type = "topdown"
    elif any(w in text for w in ["shoot", "gun", "bullet", "blast"]):
        game_type = "shooter"
    else:
        game_type = "arcade"

    word_count = len(re.findall(r"[a-z]{2,}", prompt.lower()))
    is_vague = game_type == "arcade" and word_count <= 2

    return {
        "game_type":           game_type,
        "confidence":          0.5,
        "needs_clarification": is_vague,
        "top3": [{"game_type": game_type, "confidence": 0.5}],
        "source": "keyword_fallback"
    }
