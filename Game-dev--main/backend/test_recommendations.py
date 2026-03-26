"""
Test recommendation system — play history + search history + created games.
Run from backend/: python test_recommendations.py
"""
import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

SEP  = "-" * 60
SEP2 = "=" * 60


def test_recommendation_weights():
    from app.services.recommendation_service import recommendation_service, _WEIGHTS

    print(SEP2)
    print("  PART 1 -- WEIGHTS CHECK")
    print(SEP2)
    expected = {"created": 3.0, "liked": 2.0, "searched": 1.0, "played": 1.5}
    for key, val in expected.items():
        actual = _WEIGHTS.get(key)
        status = "✓" if actual == val else f"✗ (got {actual})"
        print(f"  {key:10} weight={val}  {status}")
    print()


def test_preference_vector():
    from app.services.recommendation_service import recommendation_service

    print(SEP2)
    print("  PART 2 -- PREFERENCE VECTOR")
    print(SEP2)

    user_projects = [
        {"design_doc": {"game_type": "platformer"}},
        {"design_doc": {"game_type": "platformer"}},
    ]
    play_history = [
        {"game_type": "platformer"},
        {"game_type": "rpg"},
    ]
    search_history = [
        {"predicted_game_type": "space_shooter", "confidence": 0.87},
        {"predicted_game_type": "platformer",    "confidence": 0.75},
    ]
    liked_projects = [
        {"design_doc": {"game_type": "puzzle"}},
    ]

    # Expected:
    # platformer    = 2×3.0 + 1.5 + 0.75 = 7.25
    # rpg           = 1.5
    # space_shooter = 0.87
    # puzzle        = 2.0

    public_projects = [
        {"project_id": "p1", "user_id": "other", "design_doc": {"game_type": "platformer"}, "likes": 10, "liked_by": []},
        {"project_id": "p2", "user_id": "other", "design_doc": {"game_type": "rpg"},         "likes": 5,  "liked_by": []},
        {"project_id": "p3", "user_id": "other", "design_doc": {"game_type": "space_shooter"},"likes": 3, "liked_by": []},
        {"project_id": "p4", "user_id": "other", "design_doc": {"game_type": "puzzle"},       "likes": 8, "liked_by": []},
        {"project_id": "p5", "user_id": "other", "design_doc": {"game_type": "snake"},        "likes": 1, "liked_by": []},
    ]

    recs = recommendation_service.recommend(
        user_id="user_123",
        user_projects=user_projects,
        liked_project_ids=["p4"],   # already liked puzzle
        liked_projects=liked_projects,
        search_history=search_history,
        play_history=play_history,
        public_projects=public_projects,
        limit=10,
    )

    print("  Recommended order (expected: platformer → rpg → space_shooter → snake):")
    for i, p in enumerate(recs, 1):
        gt = (p.get("design_doc") or {}).get("game_type", "?")
        print(f"  {i}. {gt} (project_id={p['project_id']})")

    print()
    order = [(p.get("design_doc") or {}).get("game_type") for p in recs]
    assert order[0] == "platformer",    f"Expected platformer first, got {order[0]}"
    assert "rpg" in order,              "Expected rpg in results"
    assert "space_shooter" in order,    "Expected space_shooter in results"
    assert "puzzle" not in order,       "puzzle should be excluded (already liked)"
    print("  ✓ All assertions passed")
    print()


async def test_storage_play_history():
    from app.services.storage import StorageManager

    print(SEP2)
    print("  PART 3 -- STORAGE PLAY HISTORY (in-memory)")
    print(SEP2)

    storage = StorageManager()
    # stays in memory mode (no MongoDB needed)

    # Create a fake user
    user = await storage.create_user({
        "email": "test@test.com",
        "username": "testuser",
        "password_hash": "x",
    })
    uid = user["user_id"]

    # Record plays
    await storage.record_user_play(uid, "proj_1", "platformer")
    await storage.record_user_play(uid, "proj_2", "rpg")
    await storage.record_user_play(uid, "proj_3", "platformer")

    history = await storage.get_user_play_history(uid)
    print(f"  Recorded {len(history)} play events:")
    for h in history:
        print(f"    project_id={h['project_id']}  game_type={h['game_type']}")

    assert len(history) == 3,                          "Expected 3 play events"
    assert history[0]["game_type"] == "platformer",    "First play should be platformer"
    assert history[1]["game_type"] == "rpg",           "Second play should be rpg"
    assert history[2]["game_type"] == "platformer",    "Third play should be platformer"
    print("  ✓ All assertions passed")
    print()


async def test_search_history():
    from app.services.storage import StorageManager

    print(SEP2)
    print("  PART 4 -- STORAGE SEARCH HISTORY (in-memory)")
    print(SEP2)

    storage = StorageManager()

    user = await storage.create_user({
        "email": "test2@test.com",
        "username": "testuser2",
        "password_hash": "x",
    })
    uid = user["user_id"]

    await storage.add_search_event(uid, {
        "query": "mario platformer",
        "predicted_game_type": "platformer",
        "confidence": 0.92,
    })
    await storage.add_search_event(uid, {
        "query": "space invaders",
        "predicted_game_type": "space_shooter",
        "confidence": 0.87,
    })

    history = await storage.get_search_history(uid)
    print(f"  Recorded {len(history)} search events:")
    for h in history:
        print(f"    query='{h['query']}'  predicted={h['predicted_game_type']}  conf={h['confidence']}")

    assert len(history) == 2,                                    "Expected 2 search events"
    assert history[0]["predicted_game_type"] == "platformer",    "First search should be platformer"
    assert history[1]["predicted_game_type"] == "space_shooter", "Second search should be space_shooter"
    print("  ✓ All assertions passed")
    print()


async def main():
    test_recommendation_weights()
    test_preference_vector()
    await test_storage_play_history()
    await test_search_history()
    print(SEP2)
    print("  ALL TESTS PASSED")
    print(SEP2)


if __name__ == "__main__":
    asyncio.run(main())
