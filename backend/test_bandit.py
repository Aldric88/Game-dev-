"""
Bandit Algorithm Test
=====================
Tests the Epsilon-Greedy Bandit in isolation and integrated
with the recommendation service.

Run from backend/:  python test_bandit.py
"""

import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

SEP  = "-" * 60
SEP2 = "=" * 60


def make_game(project_id, game_type, likes=0):
    return {
        "project_id": project_id,
        "user_id": "other_user",
        "name": f"{game_type.title()} Game ({project_id})",
        "design_doc": {"game_type": game_type},
        "likes": likes,
        "plays": likes * 2,
    }


# ─────────────────────────────────────────────────────────────
# TEST 1: win_rate starts at default for unseen games
# ─────────────────────────────────────────────────────────────
def test_default_win_rate():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit()

    rate = b.win_rate("user1", "game_never_seen")
    assert rate == 0.5, f"Expected 0.5, got {rate}"
    print("  PASS  default win_rate = 0.5 for unseen (user, game)")


# ─────────────────────────────────────────────────────────────
# TEST 2: update() correctly tracks wins and trials
# ─────────────────────────────────────────────────────────────
def test_update_tracking():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit()

    b.update("u1", "p1", liked=True)
    b.update("u1", "p1", liked=True)
    b.update("u1", "p1", liked=False)

    stats = b.stats("u1", "p1")
    assert stats["trials"] == 3,          f"Expected 3 trials, got {stats['trials']}"
    assert stats["wins"]   == 2,          f"Expected 2 wins, got {stats['wins']}"
    assert abs(stats["win_rate"] - 2/3) < 0.001, f"Expected ~0.667, got {stats['win_rate']}"
    print("  PASS  update() correctly tracks 3 trials, 2 wins -> win_rate=0.667")


# ─────────────────────────────────────────────────────────────
# TEST 3: users are isolated — one user's data doesn't affect another
# ─────────────────────────────────────────────────────────────
def test_user_isolation():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit()

    b.update("alice", "game1", liked=True)
    b.update("alice", "game1", liked=True)   # alice: 100% win rate

    b.update("bob",   "game1", liked=False)
    b.update("bob",   "game1", liked=False)  # bob: 0% win rate

    assert b.win_rate("alice", "game1") == 1.0, "Alice should be 100%"
    assert b.win_rate("bob",   "game1") == 0.0, "Bob should be 0%"
    print("  PASS  user isolation — alice=100%, bob=0% for same game")


# ─────────────────────────────────────────────────────────────
# TEST 4: rank() returns all candidates (no games dropped)
# ─────────────────────────────────────────────────────────────
def test_rank_no_games_dropped():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit(epsilon=0.0)   # pure exploit, deterministic

    candidates = [make_game(f"p{i}", "platformer") for i in range(5)]
    ranked = b.rank("user1", candidates)

    assert len(ranked) == 5, f"Expected 5 games, got {len(ranked)}"
    print("  PASS  rank() returns all 5 candidates, none dropped")


# ─────────────────────────────────────────────────────────────
# TEST 5: exploit mode — high win-rate game ranked first
# ─────────────────────────────────────────────────────────────
def test_exploit_ranks_best_first():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit(epsilon=0.0)   # pure exploit

    # Teach bandit: game_A liked 9/10, game_B liked 1/10, game_C unseen
    for _ in range(9): b.update("user1", "game_A", liked=True)
    b.update("user1", "game_A", liked=False)  # 90% win rate

    for _ in range(1): b.update("user1", "game_B", liked=True)
    for _ in range(9): b.update("user1", "game_B", liked=False)  # 10% win rate

    candidates = [
        make_game("game_B", "shooter"),
        make_game("game_C", "puzzle"),    # unseen -> default 0.5
        make_game("game_A", "platformer"),
    ]

    ranked = b.rank("user1", candidates)
    top = ranked[0]["project_id"]

    assert top == "game_A", f"Expected game_A first (90% win rate), got {top}"
    print("  PASS  exploit: game_A (90% win rate) ranked above game_B (10%) and game_C (50%)")


# ─────────────────────────────────────────────────────────────
# TEST 6: explore mode — random ordering when epsilon=1.0
# ─────────────────────────────────────────────────────────────
def test_explore_randomizes():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit(epsilon=1.0)   # pure explore

    candidates = [make_game(f"p{i}", "puzzle") for i in range(10)]
    orders = set()
    for _ in range(20):
        ranked = b.rank("user1", candidates)
        orders.add(tuple(p["project_id"] for p in ranked))

    # With pure exploration and 10 games, we should see multiple different orders
    assert len(orders) > 1, "Expected random ordering with epsilon=1.0"
    print(f"  PASS  explore: got {len(orders)} different orderings across 20 runs (epsilon=1.0)")


# ─────────────────────────────────────────────────────────────
# TEST 7: bandit learns over time (win rate improves)
# ─────────────────────────────────────────────────────────────
def test_learns_over_time():
    from app.ml.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit()

    uid, pid = "learner", "game_X"

    rate_before = b.win_rate(uid, pid)  # 0.5 (default)

    # User likes it 8 out of 10 times
    for _ in range(8): b.update(uid, pid, liked=True)
    for _ in range(2): b.update(uid, pid, liked=False)

    rate_after = b.win_rate(uid, pid)  # should be 0.8

    assert rate_before == 0.5,               f"Before: expected 0.5, got {rate_before}"
    assert abs(rate_after - 0.8) < 0.001,   f"After: expected 0.8, got {rate_after}"
    assert rate_after > rate_before,         "Win rate should improve after positive feedback"
    print(f"  PASS  learns over time: win_rate {rate_before:.1f} -> {rate_after:.1f} after 8/10 likes")


# ─────────────────────────────────────────────────────────────
# TEST 8: integration with recommendation_service
# ─────────────────────────────────────────────────────────────
def test_recommendation_integration():
    from app.ml.bandit import EpsilonGreedyBandit, bandit as global_bandit
    from app.services.recommendation_service import RecommendationService, record_feedback

    # Use a fresh bandit for this test
    svc = RecommendationService()

    pool = [
        make_game("platformer_1", "platformer", likes=5),
        make_game("platformer_2", "platformer", likes=3),
        make_game("puzzle_1",     "puzzle",     likes=2),
        make_game("shooter_1",    "shooter",    likes=1),
    ]

    uid = "integration_user_99"

    # Simulate: user consistently likes puzzle games
    for _ in range(8): global_bandit.update(uid, "puzzle_1", liked=True)
    for _ in range(2): global_bandit.update(uid, "puzzle_1", liked=False)

    # Simulate: user ignores platformers
    for _ in range(8): global_bandit.update(uid, "platformer_1", liked=False)

    recs = svc.recommend(
        user_id="integration_user_99",
        user_projects=[],
        liked_project_ids=[],
        liked_projects=[],
        search_history=[{"predicted_game_type": "puzzle", "confidence": 0.9}],
        public_projects=pool,
        limit=4,
    )

    assert len(recs) > 0, "Should return at least 1 recommendation"
    print(f"  PASS  integration: recommendation_service returned {len(recs)} results with bandit active")

    # record_feedback works without error
    record_feedback(uid, "puzzle_1", liked=True)
    print("  PASS  record_feedback() works without error")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print(SEP2)
    print("  Epsilon-Greedy Bandit Test Suite")
    print(SEP2)
    print()

    tests = [
        ("Default win rate for unseen games",         test_default_win_rate),
        ("update() tracks trials and wins",            test_update_tracking),
        ("User isolation",                             test_user_isolation),
        ("rank() drops no candidates",                 test_rank_no_games_dropped),
        ("Exploit: best win-rate ranked first",        test_exploit_ranks_best_first),
        ("Explore: randomizes order at epsilon=1.0",   test_explore_randomizes),
        ("Learns over time from feedback",             test_learns_over_time),
        ("Integration with recommendation_service",    test_recommendation_integration),
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

    print(SEP2)
    print(f"  Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(SEP2)
