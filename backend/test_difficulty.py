"""
Difficulty Classifier Test
===========================
Tests the Perceptron-based Game Difficulty Classifier from scratch.

Run from backend/:  python test_difficulty.py
"""

import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

SEP  = "-" * 60
SEP2 = "=" * 60


def make_doc(mechanics, entities, description=""):
    return {"mechanics": mechanics, "entities": entities, "description": description}


# ─────────────────────────────────────────────────────────────
# TEST 1: Feature extraction
# ─────────────────────────────────────────────────────────────
def test_feature_extraction():
    from app.ml.difficulty_classifier import _extract_features

    doc = make_doc(
        mechanics=["shoot", "dodge", "upgrade", "boss fight", "level up"],
        entities=["Player", "Enemy", "Boss", "PowerUp", "Weapon", "Shield"],
        description="boss fight with upgrades and hazards to dodge"
    )
    features = _extract_features(doc)

    assert len(features) == 5,          f"Expected 5 features, got {len(features)}"
    assert features[0] == 5/10,         f"mechanic_count wrong: {features[0]}"
    assert features[1] == 6/12,         f"entity_count wrong: {features[1]}"
    assert features[2] == 1.0,          f"has_boss should be 1.0: {features[2]}"
    assert features[3] == 1.0,          f"has_upgrades should be 1.0: {features[3]}"
    assert features[4] == 1.0,          f"has_hazards should be 1.0: {features[4]}"
    print("  PASS  feature extraction: 5 features correct (counts + binary flags)")


# ─────────────────────────────────────────────────────────────
# TEST 2: Simple game → Easy
# ─────────────────────────────────────────────────────────────
def test_easy_prediction():
    from app.ml.difficulty_classifier import predict_difficulty

    doc = make_doc(
        mechanics=["tap to fly", "gravity"],
        entities=["Bird", "Pipe"],
        description="tap to fly avoid pipes simple"
    )
    result = predict_difficulty(doc)
    assert result["difficulty"] == "Easy", \
        f"Simple flappy bird should be Easy, got {result['difficulty']}"
    print(f"  PASS  flappy bird -> Easy  (scores: {result['scores']})")


# ─────────────────────────────────────────────────────────────
# TEST 3: Complex game → Hard
# ─────────────────────────────────────────────────────────────
def test_hard_prediction():
    from app.ml.difficulty_classifier import predict_difficulty

    doc = make_doc(
        mechanics=["shoot", "dodge", "upgrade", "boss fight", "level up", "craft", "parry"],
        entities=["Player", "Enemy", "Boss", "PowerUp", "Weapon", "Shield", "Trap", "Chest"],
        description="boss fight with weapon upgrades dodge traps and level up system"
    )
    result = predict_difficulty(doc)
    assert result["difficulty"] == "Hard", \
        f"Complex game with boss+upgrades+hazards should be Hard, got {result['difficulty']}"
    print(f"  PASS  boss+upgrades+hazards game -> Hard  (scores: {result['scores']})")


# ─────────────────────────────────────────────────────────────
# TEST 4: Medium game
# ─────────────────────────────────────────────────────────────
def test_medium_prediction():
    from app.ml.difficulty_classifier import predict_difficulty

    # Tower defense: has upgrades, moderate mechanics/entities, no boss, no hazards
    doc = make_doc(
        mechanics=["place towers", "upgrade towers", "wave enemies", "gold economy"],
        entities=["Tower", "Enemy", "Gold", "Base", "Wave"],
        description="tower defense place upgrade towers stop enemy waves no boss"
    )
    result = predict_difficulty(doc)
    assert result["difficulty"] == "Medium", \
        f"Tower defense should be Medium, got {result['difficulty']}"
    print(f"  PASS  tower defense -> Medium  (scores: {result['scores']})")


# ─────────────────────────────────────────────────────────────
# TEST 5: Adding boss makes it harder
# ─────────────────────────────────────────────────────────────
def test_boss_increases_difficulty():
    from app.ml.difficulty_classifier import predict_difficulty

    no_boss = make_doc(
        mechanics=["jump", "shoot", "dodge"],
        entities=["Player", "Enemy"],
        description="shoot enemies and dodge"
    )
    with_boss = make_doc(
        mechanics=["jump", "shoot", "dodge", "boss fight", "upgrade", "level up"],
        entities=["Player", "Enemy", "Boss", "PowerUp", "Weapon"],
        description="boss fight with upgrades dodge hazards"
    )

    result_no_boss   = predict_difficulty(no_boss)
    result_with_boss = predict_difficulty(with_boss)

    no_boss_hard_score   = result_no_boss["scores"]["Hard"]
    with_boss_hard_score = result_with_boss["scores"]["Hard"]

    assert with_boss_hard_score > no_boss_hard_score, \
        f"Boss game should score higher on Hard: {with_boss_hard_score} vs {no_boss_hard_score}"
    print(f"  PASS  adding boss raises Hard score: {no_boss_hard_score:.3f} -> {with_boss_hard_score:.3f}")


# ─────────────────────────────────────────────────────────────
# TEST 6: Output structure is correct
# ─────────────────────────────────────────────────────────────
def test_output_structure():
    from app.ml.difficulty_classifier import predict_difficulty, FEATURE_NAMES

    doc = make_doc(["jump"], ["Player"])
    result = predict_difficulty(doc)

    assert "difficulty"   in result, "Missing 'difficulty' key"
    assert "scores"       in result, "Missing 'scores' key"
    assert "features"     in result, "Missing 'features' key"
    assert "explanation"  in result, "Missing 'explanation' key"
    assert result["difficulty"] in ["Easy", "Medium", "Hard"], \
        f"Invalid difficulty: {result['difficulty']}"
    assert set(result["scores"].keys()) == {"Easy", "Medium", "Hard"}, \
        f"Scores should have all 3 classes: {result['scores'].keys()}"
    assert set(result["features"].keys()) == set(FEATURE_NAMES), \
        "Features dict keys don't match FEATURE_NAMES"
    print("  PASS  output has all required keys with correct structure")


# ─────────────────────────────────────────────────────────────
# TEST 7: Perceptron weight update (learning rule)
# ─────────────────────────────────────────────────────────────
def test_perceptron_learns():
    from app.ml.difficulty_classifier import MultiClassPerceptron, CLASSES

    p = MultiClassPerceptron(n_features=5, classes=CLASSES, learning_rate=0.1)

    X = [[0.1, 0.1, 0.0, 0.0, 0.0]] * 10   # Easy examples
    y = ["Easy"] * 10

    acc_before = p.accuracy(X, y)
    p.train(X, y, epochs=50)
    acc_after = p.accuracy(X, y)

    assert acc_after >= acc_before, \
        f"Accuracy should not decrease after training: {acc_before} -> {acc_after}"
    print(f"  PASS  perceptron learns: accuracy {acc_before:.0%} -> {acc_after:.0%} on simple examples")


# ─────────────────────────────────────────────────────────────
# TEST 8: Explanation text is generated
# ─────────────────────────────────────────────────────────────
def test_explanation_generated():
    from app.ml.difficulty_classifier import predict_difficulty

    hard_doc = make_doc(
        mechanics=["shoot", "dodge", "boss fight", "upgrade", "level up"],
        entities=["Player", "Enemy", "Boss"],
        description="boss fight dodge traps upgrade weapons"
    )
    result = predict_difficulty(hard_doc)
    assert len(result["explanation"]) > 10, "Explanation should be non-empty"
    assert isinstance(result["explanation"], str), "Explanation should be a string"
    print(f"  PASS  explanation: \"{result['explanation']}\"")


# ─────────────────────────────────────────────────────────────
# VISUAL: Show predictions for real game scenarios
# ─────────────────────────────────────────────────────────────
def show_predictions():
    from app.ml.difficulty_classifier import predict_difficulty

    print()
    print("  Sample game predictions:")
    print(f"  {'Game':<35} {'Difficulty':<10} {'Easy':>7} {'Medium':>8} {'Hard':>7}")
    print(f"  {'-'*35} {'-'*9} {'-'*7} {'-'*8} {'-'*7}")

    scenarios = [
        ("Flappy Bird clone",
         make_doc(["tap to fly", "gravity"], ["Bird", "Pipe"], "tap fly avoid pipes")),

        ("Simple Snake",
         make_doc(["eat food", "grow longer", "avoid walls"], ["Snake", "Food"], "basic snake")),

        ("Classic Platformer",
         make_doc(["jump", "run", "collect coins", "avoid enemies"],
                  ["Player", "Enemy", "Coin", "Platform"], "collect coins avoid enemies")),

        ("Tower Defense",
         make_doc(["place towers", "upgrade towers", "wave enemies"],
                  ["Tower", "Enemy", "Gold", "Base"], "place upgrade towers stop waves")),

        ("Space Shooter + Boss",
         make_doc(["shoot", "dodge", "upgrade", "boss fight"],
                  ["Ship", "Alien", "Boss", "PowerUp"], "boss fight weapon upgrade dodge")),

        ("Zombie Survival RPG",
         make_doc(["survive waves", "upgrade", "craft", "boss fight", "level up", "dodge traps"],
                  ["Player", "Zombie", "Boss", "Weapon", "Barricade", "Trap", "Chest"],
                  "zombie survival boss fight crafting upgrades dodge traps level up")),
    ]

    for name, doc in scenarios:
        result = predict_difficulty(doc)
        d = result["difficulty"]
        s = result["scores"]
        print(f"  {name:<35} {d:<10} {s['Easy']:>7.3f} {s['Medium']:>8.3f} {s['Hard']:>7.3f}")
    print()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print(SEP2)
    print("  Game Difficulty Classifier (Perceptron) Test Suite")
    print(SEP2)
    print()

    tests = [
        ("Feature extraction",                  test_feature_extraction),
        ("Easy prediction (flappy bird)",        test_easy_prediction),
        ("Hard prediction (boss+upgrades)",      test_hard_prediction),
        ("Medium prediction (platformer)",       test_medium_prediction),
        ("Boss increases difficulty score",      test_boss_increases_difficulty),
        ("Output structure is correct",          test_output_structure),
        ("Perceptron learns from examples",      test_perceptron_learns),
        ("Explanation text is generated",        test_explanation_generated),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        print(f"  [{name}]")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {e}")
            failed += 1
        print()

    show_predictions()

    print(SEP2)
    print(f"  Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(SEP2)
