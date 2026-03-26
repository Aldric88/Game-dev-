"""
Dynamic Model Trainer
======================
Async retraining pipeline that merges the base training JSON with
user-contributed examples from MongoDB, then hot-reloads the classifier.

Called automatically by ml_feedback.py when the pending example count
crosses RETRAIN_THRESHOLD.
"""

import asyncio
import json
import logging
import pickle
import random
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.storage import StorageManager

logger = logging.getLogger(__name__)

BASE_DIR        = Path(__file__).parent
DATA_PATH       = BASE_DIR / "training_data" / "game_prompts.json"
MODEL_PATH      = BASE_DIR / "models" / "game_type_classifier.pkl"
VECTORIZER_PATH = BASE_DIR / "models" / "vectorizer.pkl"

# Guard: only one retrain job at a time
_retraining_lock = asyncio.Lock()


def _load_base_data() -> tuple[list[str], list[str]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    texts  = [item["text"]  for item in raw["data"]]
    labels = [item["label"] for item in raw["data"]]
    return texts, labels


def _augment(texts: list[str], labels: list[str]) -> tuple[list[str], list[str]]:
    random.seed(42)
    synonyms = {
        "make":   ["create", "build", "generate", "design"],
        "game":   ["clone", "project", "prototype"],
        "simple": ["basic", "easy", "minimal"],
        "a":      ["an", "the"],
    }
    aug_texts, aug_labels = list(texts), list(labels)
    for text, label in zip(texts, labels):
        aug_texts.append(text.capitalize())
        aug_labels.append(label)
        words = text.split()
        new_words = []
        swapped = False
        for w in words:
            if not swapped and w.lower() in synonyms:
                options = [s for s in synonyms[w.lower()] if s != w.lower()]
                if options:
                    new_words.append(random.choice(options))
                    swapped = True
                    continue
            new_words.append(w)
        if swapped:
            aug_texts.append(" ".join(new_words))
            aug_labels.append(label)
    return aug_texts, aug_labels


def _train_pipeline(texts: list[str], labels: list[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    from sklearn.pipeline import Pipeline, FeatureUnion

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.15, random_state=42, stratify=labels
    )

    pipeline = Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(
                ngram_range=(1, 2), min_df=1, max_df=0.95,
                sublinear_tf=True, strip_accents="unicode",
                analyzer="word", token_pattern=r"\w{1,}",
            )),
            ("char", TfidfVectorizer(
                ngram_range=(2, 4), min_df=1, max_df=0.95,
                sublinear_tf=True, strip_accents="unicode",
                analyzer="char_wb",
            )),
        ])),
        ("clf", LogisticRegression(C=5.0, max_iter=1000, solver="lbfgs", random_state=42)),
    ])

    pipeline.fit(X_train, y_train)
    acc = accuracy_score(y_test, pipeline.predict(X_test))
    return pipeline, acc


def _save_model(pipeline) -> None:
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipeline, f)
    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(pipeline.named_steps["features"], f)


async def retrain(storage: "StorageManager") -> dict:
    """
    Full retrain cycle:
      1. Load base JSON training data
      2. Fetch user examples from MongoDB
      3. Merge, augment, train
      4. Save .pkl files
      5. Hot-reload classifier singleton
      6. Mark examples as trained

    Returns a summary dict with stats.
    """
    if _retraining_lock.locked():
        logger.info("Retrain already in progress — skipping.")
        return {"status": "skipped", "reason": "already_running"}

    async with _retraining_lock:
        logger.info("Dynamic retraining started.")

        # Run CPU-bound training in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _retrain_sync, await storage.get_all_ml_examples())

        if result["status"] == "ok":
            # Mark all pending examples as trained
            await storage.mark_ml_examples_trained()
            # Hot-reload the classifier singleton
            from app.ml.classifier import reload_model
            reloaded = reload_model()
            result["reloaded"] = reloaded

        logger.info("Dynamic retraining complete: %s", result)
        return result


def _retrain_sync(user_examples: list[dict]) -> dict:
    """Runs in a thread pool — no async here."""
    try:
        base_texts, base_labels = _load_base_data()

        # Merge user examples (only high-confidence, trained or not)
        user_texts  = [e["text"]  for e in user_examples if e.get("confidence", 0) >= 0.70]
        user_labels = [e["label"] for e in user_examples if e.get("confidence", 0) >= 0.70]

        all_texts  = base_texts  + user_texts
        all_labels = base_labels + user_labels

        aug_texts, aug_labels = _augment(all_texts, all_labels)
        pipeline, accuracy    = _train_pipeline(aug_texts, aug_labels)
        _save_model(pipeline)

        return {
            "status":        "ok",
            "base_examples": len(base_texts),
            "user_examples": len(user_texts),
            "total_after_aug": len(aug_texts),
            "accuracy":      round(accuracy, 4),
        }

    except Exception as exc:
        logger.error("Retraining failed: %s", exc, exc_info=True)
        return {"status": "error", "reason": str(exc)}
