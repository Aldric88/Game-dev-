"""
Chat Intent Classifier
======================
Algorithm : TF-IDF (unigram + bigram) + LinearSVC
Task      : Multi-class classification of user chat messages
Classes   : add_feature | fix_bug | change_visual | balance_mechanic
            | explain_code | general

How it works
------------
1. Raw message text is vectorised with TF-IDF (top 1 000 features,
   1–2 grams, English stop-words removed).
2. A LinearSVC (support vector machine with a linear kernel) maps the
   TF-IDF vector to one of the six intent classes.
3. The trained pipeline is serialised to disk (intent_classifier.pkl)
   and reloaded on every server start so inference is instant.

Training data
-------------
Baked-in labelled examples (~35 per class) — realistic user messages
a developer might type into the game editor chat.  The model auto-
retrains on first call if no saved model exists.

Integration
-----------
Called from ai_orchestrator.chat_reply() to pick a specialised system
prompt per intent, so the AI gives targeted answers instead of a generic
response for every message type.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
MODEL_PATH = BASE_DIR / "models" / "intent_classifier.pkl"

_pipeline: Pipeline | None = None

# ── Training data ─────────────────────────────────────────────────────────────

_TRAINING_DATA: list[tuple[str, str]] = [
    # ── add_feature ──────────────────────────────────────────────────────────
    ("add double jump",                                          "add_feature"),
    ("add a shield power up",                                    "add_feature"),
    ("add coins that the player can collect",                    "add_feature"),
    ("can you add an enemy that shoots",                         "add_feature"),
    ("add a boss fight at the end",                              "add_feature"),
    ("include a health bar for the player",                      "add_feature"),
    ("add a dash ability",                                       "add_feature"),
    ("add wall jumping",                                         "add_feature"),
    ("put in a score counter",                                   "add_feature"),
    ("add checkpoints to the level",                             "add_feature"),
    ("add an inventory system",                                  "add_feature"),
    ("include a timer",                                          "add_feature"),
    ("add sound effects when the player jumps",                  "add_feature"),
    ("add a second player",                                      "add_feature"),
    ("add a map or minimap",                                     "add_feature"),
    ("add power ups like speed boost",                           "add_feature"),
    ("include a lives system",                                   "add_feature"),
    ("add an enemy that follows the player",                     "add_feature"),
    ("add a shooting mechanic",                                  "add_feature"),
    ("add moving platforms",                                     "add_feature"),
    ("include a high score leaderboard",                         "add_feature"),
    ("add spikes as obstacles",                                  "add_feature"),
    ("add a pause menu",                                         "add_feature"),
    ("add a game over screen",                                   "add_feature"),
    ("add a win condition when all coins collected",             "add_feature"),
    ("include an upgrade shop",                                  "add_feature"),
    ("add a jetpack",                                            "add_feature"),
    ("add combo multiplier to score",                            "add_feature"),
    ("include a respawn point",                                  "add_feature"),
    ("add glide ability",                                        "add_feature"),
    ("add a knockback effect",                                   "add_feature"),
    ("include a stamina bar",                                    "add_feature"),
    ("add teleport ability",                                     "add_feature"),
    ("add destructible terrain",                                 "add_feature"),
    ("add a grappling hook",                                     "add_feature"),

    # ── fix_bug ──────────────────────────────────────────────────────────────
    ("the player falls through the floor",                       "fix_bug"),
    ("game crashes when i jump",                                 "fix_bug"),
    ("there is an error in the player script",                   "fix_bug"),
    ("the enemy doesnt move",                                    "fix_bug"),
    ("the score doesnt update",                                  "fix_bug"),
    ("collision is not working",                                 "fix_bug"),
    ("player gets stuck in the wall",                            "fix_bug"),
    ("the bullets go the wrong direction",                       "fix_bug"),
    ("the game freezes after a few seconds",                     "fix_bug"),
    ("i cant jump on to the platforms",                          "fix_bug"),
    ("the health bar goes below zero",                           "fix_bug"),
    ("the enemy overlaps with the player",                       "fix_bug"),
    ("cant collect coins fix",                                   "fix_bug"),
    ("not working properly",                                     "fix_bug"),
    ("the animation is broken",                                  "fix_bug"),
    ("null pointer error in script",                             "fix_bug"),
    ("player spawns outside the map",                            "fix_bug"),
    ("the timer counts up instead of down",                      "fix_bug"),
    ("the game doesnt end when health reaches zero",             "fix_bug"),
    ("the background is missing",                                "fix_bug"),
    ("the jump does not work",                                   "fix_bug"),
    ("error on line 24",                                         "fix_bug"),
    ("the shooting breaks after a while",                        "fix_bug"),
    ("player clips through walls",                               "fix_bug"),
    ("the respawn is broken",                                    "fix_bug"),
    ("enemy spawns inside wall",                                 "fix_bug"),
    ("the level doesnt load",                                    "fix_bug"),
    ("wrong collision layer",                                    "fix_bug"),
    ("the attack animation plays twice",                         "fix_bug"),
    ("the game lags every few seconds",                          "fix_bug"),
    ("the coins arent disappearing when collected",              "fix_bug"),
    ("score resets unexpectedly",                                "fix_bug"),
    ("boss doesnt take damage",                                  "fix_bug"),
    ("double jump not registering second jump",                  "fix_bug"),
    ("the player moves in the wrong direction",                  "fix_bug"),

    # ── change_visual ────────────────────────────────────────────────────────
    ("make the background blue",                                 "change_visual"),
    ("change the player color to red",                           "change_visual"),
    ("make the game look more retro",                            "change_visual"),
    ("add a neon visual style",                                  "change_visual"),
    ("make the player bigger",                                   "change_visual"),
    ("change the font to something pixel",                       "change_visual"),
    ("add particle effects when jumping",                        "change_visual"),
    ("make the background darker",                               "change_visual"),
    ("change the enemy sprite to look scarier",                  "change_visual"),
    ("add a glow effect to coins",                               "change_visual"),
    ("make the UI cleaner",                                      "change_visual"),
    ("change the color scheme to purple and black",              "change_visual"),
    ("add a trail effect to the player",                         "change_visual"),
    ("make the platforms look like stone",                       "change_visual"),
    ("change the background to a night sky",                     "change_visual"),
    ("make coins look like gems",                                "change_visual"),
    ("add screen shake on hit",                                  "change_visual"),
    ("make the health bar green",                                "change_visual"),
    ("change the bullets to laser beams visually",               "change_visual"),
    ("make it look more cartoonish",                             "change_visual"),
    ("add a shadow under the player",                            "change_visual"),
    ("make the game look minimalist",                            "change_visual"),
    ("change the background color to gradient",                  "change_visual"),
    ("add flashing effect when player takes damage",             "change_visual"),
    ("make the player sprite smaller",                           "change_visual"),
    ("change theme to space",                                    "change_visual"),
    ("make it look more colorful",                               "change_visual"),
    ("add a vignette effect",                                    "change_visual"),
    ("change the enemy color to orange",                         "change_visual"),
    ("make the ground look grassy",                              "change_visual"),
    ("add blood or hit particles",                               "change_visual"),
    ("change the coins to stars",                                "change_visual"),
    ("make the background scroll",                               "change_visual"),
    ("add dust particles when landing",                          "change_visual"),
    ("make it look like a pixel dungeon",                        "change_visual"),

    # ── balance_mechanic ─────────────────────────────────────────────────────
    ("make the jump bigger",                                     "balance_mechanic"),
    ("the enemies are too fast",                                 "balance_mechanic"),
    ("increase the player speed",                                "balance_mechanic"),
    ("make gravity lower",                                       "balance_mechanic"),
    ("reduce the enemy damage",                                  "balance_mechanic"),
    ("increase health to 200",                                   "balance_mechanic"),
    ("make the game harder",                                     "balance_mechanic"),
    ("the jump height is too low",                               "balance_mechanic"),
    ("make the player run faster",                               "balance_mechanic"),
    ("reduce the respawn time",                                  "balance_mechanic"),
    ("make the bullets faster",                                  "balance_mechanic"),
    ("the game is too easy",                                     "balance_mechanic"),
    ("increase the number of enemies",                           "balance_mechanic"),
    ("make the boss have more health",                           "balance_mechanic"),
    ("reduce friction on ice",                                   "balance_mechanic"),
    ("make the player heavier",                                  "balance_mechanic"),
    ("slow down the enemy spawn rate",                           "balance_mechanic"),
    ("increase jump velocity",                                   "balance_mechanic"),
    ("make the gravity stronger",                                "balance_mechanic"),
    ("decrease the cooldown on dash",                            "balance_mechanic"),
    ("enemies should deal more damage",                          "balance_mechanic"),
    ("increase coin value to 10",                                "balance_mechanic"),
    ("make the level longer",                                    "balance_mechanic"),
    ("reduce player knockback",                                  "balance_mechanic"),
    ("the acceleration is too slow",                             "balance_mechanic"),
    ("make the shooting rate faster",                            "balance_mechanic"),
    ("make enemies slower",                                      "balance_mechanic"),
    ("increase the number of lives",                             "balance_mechanic"),
    ("lower the enemy health",                                   "balance_mechanic"),
    ("increase the speed of the ball",                           "balance_mechanic"),
    ("make the platforms wider",                                 "balance_mechanic"),
    ("decrease jump cooldown",                                   "balance_mechanic"),
    ("make the game easier for beginners",                       "balance_mechanic"),
    ("increase the spawn rate of power ups",                     "balance_mechanic"),
    ("make score multiplier stack faster",                       "balance_mechanic"),

    # ── explain_code ─────────────────────────────────────────────────────────
    ("what does this script do",                                 "explain_code"),
    ("explain the player movement code",                         "explain_code"),
    ("how does the collision system work",                       "explain_code"),
    ("why is there a timer in this file",                        "explain_code"),
    ("what is this function doing",                              "explain_code"),
    ("can you explain how the enemy ai works",                   "explain_code"),
    ("what does move and slide do",                              "explain_code"),
    ("explain what coyote time is",                              "explain_code"),
    ("how does the shooting mechanic work",                      "explain_code"),
    ("what is the purpose of this variable",                     "explain_code"),
    ("explain the score system",                                 "explain_code"),
    ("how does the level loading work",                          "explain_code"),
    ("what does the physics process function do",                "explain_code"),
    ("can you walk me through the enemy patrol logic",           "explain_code"),
    ("explain how the health system is implemented",             "explain_code"),
    ("what are signals in godot",                                "explain_code"),
    ("how does the animation state machine work",                "explain_code"),
    ("explain the jump buffer logic",                            "explain_code"),
    ("what is the delta parameter in physics process",           "explain_code"),
    ("how does the scene switching work",                        "explain_code"),
    ("explain the singleton pattern in this code",               "explain_code"),
    ("what does ready do",                                       "explain_code"),
    ("explain the input handling in this game",                  "explain_code"),
    ("how does the save system work",                            "explain_code"),
    ("what is the gravity constant doing",                       "explain_code"),
    ("explain why there are two movement functions",             "explain_code"),
    ("how is damage calculated",                                 "explain_code"),
    ("what does the area entered signal do",                     "explain_code"),
    ("explain the state machine logic",                          "explain_code"),
    ("how does pathfinding work in this game",                   "explain_code"),
    ("what is lerp used for here",                               "explain_code"),
    ("explain how projectiles are spawned",                      "explain_code"),
    ("what does the modulate property do",                       "explain_code"),
    ("how does the camera follow the player",                    "explain_code"),
    ("explain the spawn system",                                 "explain_code"),

    # ── general ──────────────────────────────────────────────────────────────
    ("how do i export the game",                                 "general"),
    ("what is godot",                                            "general"),
    ("how do i add a sound file",                                "general"),
    ("can i run this on mobile",                                 "general"),
    ("how do i share this game",                                 "general"),
    ("what file format does godot use",                          "general"),
    ("how do i open this in godot editor",                       "general"),
    ("what version of godot is this",                            "general"),
    ("how do i add a new scene",                                 "general"),
    ("can i publish this game",                                  "general"),
    ("how do i change the window size",                          "general"),
    ("what is gdscript",                                         "general"),
    ("how does the game save progress",                          "general"),
    ("can i add music to the game",                              "general"),
    ("how do i create a new level",                              "general"),
    ("what is a node in godot",                                  "general"),
    ("how do i use the godot asset store",                       "general"),
    ("can you generate a completely new game for me",            "general"),
    ("how do i make the game fullscreen",                        "general"),
    ("what are the controls",                                    "general"),
    ("how do i add a loading screen",                            "general"),
    ("can this game be multiplayer",                             "general"),
    ("how do i connect a button",                                "general"),
    ("what does the assembler agent do",                         "general"),
    ("how is the game generated",                                "general"),
    ("what is forgeai",                                          "general"),
    ("how do i reset the game",                                  "general"),
    ("can i change the game genre",                              "general"),
    ("how do i delete a node",                                   "general"),
    ("what frameworks are supported",                            "general"),
    ("how many credits does generation cost",                    "general"),
    ("how do i report a bug in forgeai",                         "general"),
    ("what is the difference between scene and script",          "general"),
    ("can i import my own assets",                               "general"),
    ("how do i make the player jump higher in general",          "general"),
]

# ── System prompts per intent ─────────────────────────────────────────────────

INTENT_SYSTEM_PROMPTS: dict[str, str] = {
    "add_feature": (
        "You are modifying an existing Godot 4.x game to ADD A NEW FEATURE. "
        "Identify exactly which file(s) need to change. "
        "Output each modified file in full using ===FILE: filename===\\n<content>\\n===END FILE=== format. "
        "Explain briefly what you added and why."
    ),
    "fix_bug": (
        "You are debugging an existing Godot 4.x game. The user has reported a BUG or error. "
        "Diagnose the root cause first, then provide the complete corrected file content. "
        "Output each fixed file using ===FILE: filename===\\n<content>\\n===END FILE=== format. "
        "Explain what was wrong and how you fixed it."
    ),
    "change_visual": (
        "You are changing the VISUAL APPEARANCE of an existing Godot 4.x game. "
        "Focus on colors, sizes, effects, and visual properties only. "
        "Output each modified file using ===FILE: filename===\\n<content>\\n===END FILE=== format. "
        "Keep gameplay logic unchanged."
    ),
    "balance_mechanic": (
        "You are TUNING GAME MECHANICS in an existing Godot 4.x game. "
        "Adjust numerical constants: speed, jump velocity, gravity, health, damage, timing values. "
        "Output each modified file using ===FILE: filename===\\n<content>\\n===END FILE=== format. "
        "State exactly which values you changed and what they were before."
    ),
    "explain_code": (
        "You are EXPLAINING existing Godot 4.x game code. "
        "Give a clear, developer-friendly explanation of what the code does and why. "
        "Do NOT modify any files unless the user explicitly asks for a change. "
        "Use examples and analogies where helpful."
    ),
    "general": (
        "You are an expert game development assistant for the ForgeAI platform. "
        "Answer the user's question clearly and concisely. "
        "If the question is about game modifications, ask for clarification on what to change."
    ),
}

INTENT_LABELS: dict[str, str] = {
    "add_feature":      "Add Feature",
    "fix_bug":          "Fix Bug",
    "change_visual":    "Change Visual",
    "balance_mechanic": "Balance Mechanic",
    "explain_code":     "Explain Code",
    "general":          "General",
}


# ── Model lifecycle ───────────────────────────────────────────────────────────

def _train() -> Pipeline:
    """Train TF-IDF + LinearSVC on the baked-in labelled examples."""
    texts  = [t for t, _ in _TRAINING_DATA]
    labels = [l for _, l in _TRAINING_DATA]

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=1000, stop_words="english")
    svc        = CalibratedClassifierCV(LinearSVC(max_iter=2000, C=1.0))
    pipeline   = Pipeline([("tfidf", vectorizer), ("clf", svc)])
    pipeline.fit(texts, labels)
    return pipeline


def _load_or_train() -> Pipeline:
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as f:
                _pipeline = pickle.load(f)
            logger.info("Intent classifier loaded from %s", MODEL_PATH)
            return _pipeline
        except Exception as exc:
            logger.warning("Could not load intent model, retraining: %s", exc)

    _pipeline = _train()
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(_pipeline, f)
    logger.info("Intent classifier trained and saved to %s", MODEL_PATH)
    return _pipeline


# ── Public API ────────────────────────────────────────────────────────────────

def classify_intent(message: str) -> dict[str, Any]:
    """
    Classify a chat message into one of six intent classes.

    Returns
    -------
    {
        "intent":      "fix_bug",
        "label":       "Fix Bug",
        "confidence":  0.87,
        "system_prompt": "<specialised prompt for this intent>"
    }
    """
    pipeline = _load_or_train()
    proba    = pipeline.predict_proba([message])[0]
    classes  = pipeline.classes_
    best_idx = int(proba.argmax())
    intent   = classes[best_idx]
    conf     = float(proba[best_idx])

    return {
        "intent":        intent,
        "label":         INTENT_LABELS.get(intent, intent),
        "confidence":    round(conf, 3),
        "system_prompt": INTENT_SYSTEM_PROMPTS[intent],
    }
