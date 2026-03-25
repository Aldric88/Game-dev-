"""
Game Type Classifier — Training Script
=======================================
Trains a text classifier to predict game type from a user's prompt.
Replaces the brittle keyword matching in game_inference.py.

Usage:
    python -m app.ml.train_classifier

Output:
    app/ml/models/game_type_classifier.pkl   ← trained model
    app/ml/models/vectorizer.pkl             ← fitted TF-IDF vectorizer

Requirements:
    scikit-learn, numpy (add to requirements.txt)
"""

import json
import os
import pickle
import random
import numpy as np
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DATA_PATH   = BASE_DIR / "training_data" / "game_prompts.json"
MODELS_DIR  = BASE_DIR / "models"
MODEL_PATH  = MODELS_DIR / "game_type_classifier.pkl"
VECTORIZER_PATH = MODELS_DIR / "vectorizer.pkl"

MODELS_DIR.mkdir(exist_ok=True)


# ── Step 1: Load training data ─────────────────────────────────────────────────
def load_data():
    with open(DATA_PATH, "r") as f:
        raw = json.load(f)

    texts  = [item["text"] for item in raw["data"]]
    labels = [item["label"] for item in raw["data"]]

    print(f"Loaded {len(texts)} training examples")
    print(f"Game types: {sorted(set(labels))}")
    print()

    # Show distribution
    from collections import Counter
    dist = Counter(labels)
    for game_type, count in sorted(dist.items()):
        print(f"  {game_type:<20} {count} examples")
    print()

    return texts, labels


# ── Step 2: Data augmentation ──────────────────────────────────────────────────
def augment(texts, labels):
    """
    Simple augmentation: adds common rewrites for each example.
    Multiplies training data ~3x without any API calls.
    """
    random.seed(42)
    synonyms = {
        "make":   ["create", "build", "generate", "design"],
        "game":   ["clone", "project", "prototype"],
        "simple": ["basic", "easy", "minimal"],
        "a":      ["an", "the"],
    }

    aug_texts, aug_labels = list(texts), list(labels)

    for text, label in zip(texts, labels):
        words = text.split()

        # Variant 1: capitalise first letter
        aug_texts.append(text.capitalize())
        aug_labels.append(label)

        # Variant 2: swap first verb synonym
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

    print(f"After augmentation: {len(aug_texts)} examples")
    return aug_texts, aug_labels


# ── Step 3: Build pipeline & train ────────────────────────────────────────────
def train(texts, labels):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import classification_report, accuracy_score
    from sklearn.pipeline import Pipeline, FeatureUnion

    # Split: 85% train, 15% test
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels,
        test_size=0.15,
        random_state=42,
        stratify=labels
    )

    print(f"Train size: {len(X_train)}  |  Test size: {len(X_test)}")
    print()

    # Two TF-IDF vectorizers combined via FeatureUnion:
    # 1. Word-level  - understands full words and phrases
    # 2. Char-level  - understands character substrings, handles typos naturally
    #    "platfomer" shares chars "platf","latfo","atfor" with "platformer" -> still works
    word_tfidf = TfidfVectorizer(
        ngram_range=(1, 2),     # words and two-word phrases
        min_df=1,
        max_df=0.95,
        sublinear_tf=True,
        strip_accents="unicode",
        analyzer="word",
        token_pattern=r"\w{1,}",
    )

    char_tfidf = TfidfVectorizer(
        ngram_range=(2, 4),     # 2-4 character substrings
        min_df=1,
        max_df=0.95,
        sublinear_tf=True,
        strip_accents="unicode",
        analyzer="char_wb",     # char within word boundaries
    )

    pipeline = Pipeline([
        ("features", FeatureUnion([
            ("word", word_tfidf),   # handles meaning
            ("char", char_tfidf),   # handles typos
        ])),
        ("clf", LogisticRegression(
            C=5.0,
            max_iter=1000,
            solver="lbfgs",
            random_state=42,
        )),
    ])

    # Train
    pipeline.fit(X_train, y_train)

    # Evaluate on held-out test set
    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Test Accuracy: {acc:.2%}")
    print()
    print(classification_report(y_test, y_pred))

    # Cross-validation (5-fold) for robust estimate
    cv_scores = cross_val_score(pipeline, texts, labels, cv=5, scoring="accuracy")
    print(f"Cross-val accuracy: {cv_scores.mean():.2%} (+/- {cv_scores.std():.2%})")
    print()

    return pipeline


# ── Step 4: Save the trained model ─────────────────────────────────────────────
def save_model(pipeline):
    # Save as single .pkl file (pipeline includes vectorizer + classifier)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"Model saved -> {MODEL_PATH}")

    # Also save feature union separately (word + char vectorizers)
    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(pipeline.named_steps["features"], f)
    print(f"Vectorizer saved -> {VECTORIZER_PATH}")


# ── Step 5: Quick sanity check ─────────────────────────────────────────────────
def sanity_check(pipeline):
    test_prompts = [
        ("make a mario style game",                 "platformer"),
        ("game where a bird flies through pipes",   "flappy"),
        ("build a tower defense with archers",      "tower_defense"),
        ("space invaders clone",                    "space_shooter"),
        ("classic snake game",                      "snake"),
        ("street fighter style fighting game",      "fighting"),
        ("survive waves of zombies",                "survival"),
        ("top down gta style game",                 "topdown"),
        ("car racing with drift mechanics",         "racing"),
        ("match 3 puzzle game",                     "puzzle"),
        ("rpg with dungeons and loot",              "rpg"),
        ("something like sonic but simpler",        "platformer"),
        ("tap to fly through obstacles",            "flappy"),
        ("shoot aliens from your spaceship",        "space_shooter"),
    ]

    print("-- Sanity Check ----------------------------------")
    correct = 0
    for prompt, expected in test_prompts:
        predicted = pipeline.predict([prompt])[0]
        proba     = pipeline.predict_proba([prompt])[0]
        confidence = max(proba)
        status = "OK" if predicted == expected else "FAIL"
        if predicted == expected:
            correct += 1
        print(f"  {status}  [{confidence:.0%}]  '{prompt}'")
        if predicted != expected:
            print(f"       Expected: {expected}  |  Got: {predicted}")

    print(f"\nSanity check: {correct}/{len(test_prompts)} correct")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ForgeAI — Game Type Classifier Training")
    print("=" * 55)
    print()

    texts, labels = load_data()
    texts, labels = augment(texts, labels)
    pipeline      = train(texts, labels)
    save_model(pipeline)
    sanity_check(pipeline)

    print("Done. Model ready to use in game_inference.py")
