"""
ML Feedback Service
====================
Collects training signals when users create games and triggers
automatic retraining when enough new examples accumulate.

Flow:
    User creates game (prompt + confirmed game_type)
        → record_game_creation()
            → saves example to MongoDB
            → if pending count >= RETRAIN_THRESHOLD
                → fires background retrain task
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.storage import StorageManager

logger = logging.getLogger(__name__)

# Retrain after every N new user-confirmed examples
RETRAIN_THRESHOLD = 50

# Minimum confidence to accept a signal as training data
MIN_CONFIDENCE = 0.70


async def record_game_creation(
    storage: "StorageManager",
    prompt: str,
    game_type: str,
    confidence: float = 1.0,
) -> None:
    """
    Save a confirmed game creation as a training signal.
    Fires retraining in the background if threshold is reached.

    Args:
        storage:    StorageManager instance
        prompt:     The user's original description/prompt
        game_type:  Confirmed game type (from design_doc)
        confidence: ML confidence score (1.0 for user-confirmed types)
    """
    prompt = prompt.strip()
    if not prompt or not game_type:
        return

    # Only save if confidence meets the bar
    if confidence < MIN_CONFIDENCE:
        logger.debug(
            "Skipping ML signal — confidence %.2f below threshold %.2f",
            confidence, MIN_CONFIDENCE,
        )
        return

    await storage.add_ml_example(prompt, game_type, confidence)
    logger.debug("ML signal saved: '%s' → %s (%.0f%%)", prompt[:60], game_type, confidence * 100)

    # Check threshold and trigger retrain in the background
    pending = await storage.count_pending_ml_examples()
    if pending >= RETRAIN_THRESHOLD:
        logger.info(
            "%d pending ML examples — triggering background retrain.", pending
        )
        asyncio.create_task(_background_retrain(storage))


async def _background_retrain(storage: "StorageManager") -> None:
    """Fire-and-forget retrain task. Errors are logged, never raised."""
    try:
        from app.ml.trainer import retrain
        result = await retrain(storage)
        if result["status"] == "ok":
            logger.info(
                "Auto-retrain complete — accuracy: %.2f%%, "
                "base: %d, user: %d, total: %d",
                result["accuracy"] * 100,
                result["base_examples"],
                result["user_examples"],
                result["total_after_aug"],
            )
        elif result["status"] == "skipped":
            logger.info("Auto-retrain skipped: %s", result.get("reason"))
        else:
            logger.error("Auto-retrain failed: %s", result.get("reason"))
    except Exception as exc:
        logger.error("Background retrain raised an exception: %s", exc, exc_info=True)
