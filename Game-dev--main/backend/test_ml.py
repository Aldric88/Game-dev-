"""
Detailed ML test -- classifier + recommendation engine.
Run from backend/:  python test_ml.py
"""

import asyncio
import sys
from collections import defaultdict, Counter
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME   = "game_ai_platform"

SEP  = "-" * 60
SEP2 = "=" * 60


# ----------------------------------------------------------------------------
# PART 1 -- Classifier tests
# ----------------------------------------------------------------------------

def test_classifier():
    from app.ml.classifier import predict_game_type, CONFIDENCE_THRESHOLD

    print(SEP2)
    print("  PART 1 -- GAME TYPE CLASSIFIER")
    print(SEP2)
    print(f"  Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print()

    test_cases = [
        # clear cases
        ("make a mario style platformer",             "platformer"),
        ("bird flying through pipes tap to fly",      "flappy"),
        ("snake eats food and grows longer",          "snake"),
        ("shoot aliens from your spaceship",          "space_shooter"),
        ("build towers to stop the enemy horde",      "tower_defense"),
        ("street fighting game with combos",          "fighting"),
        ("survive waves of zombies with limited ammo","survival"),
        ("top down gta style crime game",             "topdown"),
        ("car racing with drift mechanics turbo",     "racing"),
        ("match 3 puzzle with colorful gems",         "puzzle"),
        ("rpg dungeon crawler with loot and quests",  "rpg"),
        ("twin stick shooter with bullet hell",       "shooter"),
        ("old school arcade high score game",         "arcade"),
        # indirect / tricky
        ("something like sonic but simpler",          "platformer"),
        ("tap to fly through obstacles",              "flappy"),
        ("hungry worm eats apples",                   "snake"),
        ("galaga clone defend earth",                 "space_shooter"),
        ("plants vs zombies style",                   "tower_defense"),
        ("beat em up brawler",                        "fighting"),
        ("vampire survivors clone auto attacks",      "survival"),
        ("overhead adventure explore map",            "topdown"),
        ("drift king master tight corners",           "racing"),
        ("tetris style falling blocks",               "puzzle"),
        ("zelda style adventure with towns",          "rpg"),
        ("run and gun side scroller",                 "shooter"),
        # typos
        ("platfomer with jumps",                      "platformer"),
        ("zombi waives surival",                      "survival"),
        # vague (should set needs_clarification=True)
        ("make a game",                               None),
        ("something cool",                            None),
    ]

    correct = 0
    results = []

    for prompt, expected in test_cases:
        r = predict_game_type(prompt)
        predicted = r["game_type"]
        conf      = r["confidence"]
        needs_cl  = r["needs_clarification"]
        source    = r["source"]
        top3      = r["top3"]

        if expected is None:
            ok = needs_cl
        else:
            ok = (predicted == expected)
            if ok:
                correct += 1

        results.append((prompt, expected, predicted, conf, needs_cl, source, top3, ok))

    print(f"  {'PROMPT':<44} {'EXPECTED':<16} {'GOT':<20} {'CONF':>5}  STATUS")
    print(f"  {SEP}")
    for prompt, expected, predicted, conf, needs_cl, source, top3, ok in results:
        exp_str = expected or "(vague->clarify)"
        status  = "OK  " if ok else "FAIL"
        cl_tag  = "[?]" if needs_cl else "   "
        print(f"  {prompt:<44} {exp_str:<16} {predicted+' '+cl_tag:<20} {conf:>4.0%}  {status}")

    labelled    = [r for r in results if r[1] is not None]
    vague_cases = [r for r in results if r[1] is None]
    vague_ok    = sum(1 for r in vague_cases if r[7])

    print()
    print(f"  Labelled accuracy : {correct}/{len(labelled)} = {correct/len(labelled):.0%}")
    print(f"  Vague detection   : {vague_ok}/{len(vague_cases)} correctly asked for clarification")

    confs = [r[3] for r in results if r[1] is not None]
    print()
    print(f"  Avg confidence (labelled): {sum(confs)/len(confs):.1%}")
    print(f"  Min confidence           : {min(confs):.1%}")
    print(f"  Max confidence           : {max(confs):.1%}")
    print()

    print("  Top-3 breakdown for first 5 prompts:")
    for prompt, expected, predicted, conf, needs_cl, source, top3, ok in results[:5]:
        print(f"    '{prompt}'")
        for t in top3:
            marker = "<-- winner" if t["game_type"] == predicted else ""
            print(f"      {t['game_type']:<20} {t['confidence']:.1%}  {marker}")
    print()


# ----------------------------------------------------------------------------
# PART 2 -- Recommendation engine (live MongoDB data)
# ----------------------------------------------------------------------------

async def test_recommendations():
    from app.services.recommendation_service import RecommendationService
    from app.ml.classifier import predict_game_type

    print(SEP2)
    print("  PART 2 -- RECOMMENDATION ENGINE (live MongoDB data)")
    print(SEP2)

    client = AsyncIOMotorClient(MONGO_URI)
    db     = client[DB_NAME]
    users_col    = db["users"]
    projects_col = db["projects"]

    users = await users_col.find(
        {"email": {"$regex": r"^testuser\d+@forge\.ai$"}}
    ).to_list(length=20)

    if not users:
        print("  No test users found -- run seed_data.py first.")
        client.close()
        return

    all_public = await projects_col.find({"is_public": True}).sort("plays", -1).to_list(length=500)

    print(f"  Loaded {len(users)} test users, {len(all_public)} public projects")
    print()

    type_counts = Counter(
        (p.get("design_doc") or {}).get("game_type", "unknown")
        for p in all_public
    )
    print("  Public pool -- game type distribution:")
    for gt, cnt in sorted(type_counts.items()):
        bar = "#" * cnt
        print(f"    {gt:<20} {cnt:>3}  {bar}")
    print()

    rec_svc = RecommendationService()

    fake_searches = [
        "make a platformer with jumps",
        "snake game with power ups",
        "zombie survival waves",
    ]

    for user in users[:5]:
        user_id  = user["user_id"]
        username = user.get("username", user_id)

        user_projects = await projects_col.find({"user_id": user_id}).to_list(length=100)
        created_types = Counter(
            (p.get("design_doc") or {}).get("game_type", "?")
            for p in user_projects
        )

        liked_docs  = await projects_col.find(
            {"is_public": True, "liked_by": user_id}
        ).to_list(length=100)
        liked_ids   = [p["project_id"] for p in liked_docs]
        liked_types = Counter(
            (p.get("design_doc") or {}).get("game_type", "?")
            for p in liked_docs
        )

        search_history = []
        for q in fake_searches:
            r = predict_game_type(q)
            search_history.append({
                "query": q,
                "predicted_game_type": r["game_type"],
                "confidence": r["confidence"],
            })

        recs = rec_svc.recommend(
            user_id           = user_id,
            user_projects     = user_projects,
            liked_project_ids = liked_ids,
            liked_projects    = liked_docs,
            search_history    = search_history,
            public_projects   = all_public,
            limit             = 8,
        )

        prefs: dict = defaultdict(float)
        for p in user_projects:
            gt = (p.get("design_doc") or {}).get("game_type")
            if gt: prefs[gt] += 3.0
        for p in liked_docs:
            gt = (p.get("design_doc") or {}).get("game_type")
            if gt: prefs[gt] += 2.0
        for ev in search_history:
            gt   = ev.get("predicted_game_type")
            conf = float(ev.get("confidence", 0.5))
            if gt and conf >= 0.50:
                prefs[gt] += 1.0 * conf

        print(f"  {SEP}")
        print(f"  USER: {username}")
        print(f"  {SEP}")
        print(f"  Created game types : {dict(created_types)}")
        print(f"  Liked game types   : {dict(liked_types)} ({len(liked_ids)} liked)")
        print(f"  Search signals     :")
        for ev in search_history:
            print(f"    '{ev['query']}' -> {ev['predicted_game_type']} ({ev['confidence']:.0%})")
        print()
        print(f"  Preference vector  :")
        if prefs:
            for gt, score in sorted(prefs.items(), key=lambda x: x[1], reverse=True):
                bar = "|" * int(score * 2)
                print(f"    {gt:<20} score={score:.1f}  {bar}")
        else:
            print("    (no signals -- cold start)")
        print()
        print(f"  Top {len(recs)} recommendations:")
        for i, p in enumerate(recs, 1):
            gt    = (p.get("design_doc") or {}).get("game_type", "?")
            pref  = prefs.get(gt, 0.0)
            plays = p.get("plays", 0)
            likes = p.get("likes", 0)
            print(f"    {i:>2}. [{gt:<16}] pref={pref:.1f}  plays={plays:>3}  likes={likes:>2}  {p['name']}")
        print()

    # Cold start test
    print(SEP2)
    print("  COLD START TEST (brand-new user, no signals)")
    print(SEP2)
    cold_recs = rec_svc.recommend(
        user_id           = "brand-new-user-000",
        user_projects     = [],
        liked_project_ids = [],
        liked_projects    = [],
        search_history    = [],
        public_projects   = all_public,
        limit             = 6,
    )
    print("  Returns top-liked projects globally:")
    for i, p in enumerate(cold_recs, 1):
        gt = (p.get("design_doc") or {}).get("game_type", "?")
        print(f"    {i}. [{gt:<16}] likes={p.get('likes',0):>2}  plays={p.get('plays',0):>3}  {p['name']}")
    print()

    # Exclusion test
    print(SEP2)
    print("  EXCLUSION TEST (own + liked projects must not appear in recs)")
    print(SEP2)
    test_user   = users[0]
    t_id        = test_user["user_id"]
    t_projects  = await projects_col.find({"user_id": t_id}).to_list(100)
    t_liked     = await projects_col.find({"is_public": True, "liked_by": t_id}).to_list(100)
    t_liked_ids = [p["project_id"] for p in t_liked]

    excl_recs = rec_svc.recommend(
        user_id           = t_id,
        user_projects     = t_projects,
        liked_project_ids = t_liked_ids,
        liked_projects    = t_liked,
        search_history    = [],
        public_projects   = all_public,
        limit             = 50,
    )

    own_ids    = {p["project_id"] for p in t_projects}
    liked_set  = set(t_liked_ids)
    own_leak   = [p for p in excl_recs if p["project_id"] in own_ids]
    liked_leak = [p for p in excl_recs if p["project_id"] in liked_set]

    print(f"  User: {test_user.get('username')}  |  owns={len(own_ids)} projects  |  liked={len(liked_set)}")
    print(f"  Recs returned : {len(excl_recs)}")
    print(f"  Own leaking   : {len(own_leak)}  {'PASS (0 expected)' if not own_leak else 'FAIL BUG!'}")
    print(f"  Liked leaking : {len(liked_leak)}  {'PASS (0 expected)' if not liked_leak else 'FAIL BUG!'}")
    print()

    client.close()


# ----------------------------------------------------------------------------
# PART 3 -- End-to-end signal chain
# ----------------------------------------------------------------------------

def test_signal_chain():
    from app.ml.classifier import predict_game_type
    from app.services.recommendation_service import RecommendationService

    print(SEP2)
    print("  PART 3 -- END-TO-END SIGNAL CHAIN")
    print(SEP2)

    prompts = [
        "mario platformer with double jump",
        "zombie wave survival game",
        "zombie horde auto attack vampire style",
        "build towers defend from goblins",
        "shoot spaceships with laser",
    ]

    print("  Classifier -> search_history signals:")
    search_history = []
    for q in prompts:
        r = predict_game_type(q)
        search_history.append({
            "query": q,
            "predicted_game_type": r["game_type"],
            "confidence": r["confidence"],
        })
        cl = "-> ask clarification" if r["needs_clarification"] else ""
        print(f"    '{q}'")
        print(f"       -> {r['game_type']}  {r['confidence']:.0%}  [{r['source']}]  {cl}")
        top3_str = [(t["game_type"], f"{t['confidence']:.0%}") for t in r["top3"]]
        print(f"         top3: {top3_str}")
        print()

    fake_pool = [
        {"project_id": f"p{i}", "user_id": "other", "name": f"Game {i}",
         "design_doc": {"game_type": gt}, "likes": 10-i, "plays": 50-i*3}
        for i, gt in enumerate([
            "platformer","platformer","survival","survival","tower_defense",
            "space_shooter","snake","racing","puzzle","rpg"
        ])
    ]

    rec_svc = RecommendationService()
    recs = rec_svc.recommend(
        user_id="test-e2e",
        user_projects=[],
        liked_project_ids=[],
        liked_projects=[],
        search_history=search_history,
        public_projects=fake_pool,
        limit=10,
    )

    print("  Recommendation order from search-only signals:")
    for i, p in enumerate(recs, 1):
        gt = (p.get("design_doc") or {}).get("game_type")
        print(f"    {i}. [{gt:<16}]  {p['name']}")
    print()


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print()
    print(SEP2)
    print("  ForgeAI -- ML Algorithm Detailed Test Suite")
    print(SEP2)
    print()

    test_classifier()
    test_signal_chain()
    asyncio.run(test_recommendations())

    print(SEP2)
    print("  All tests complete.")
    print(SEP2)
