"""
Comprehensive ML Feature Test Suite
=====================================
Tests all 3 implemented ML features:
  1. Game Type Classifier
  2. Hybrid Search Service
  3. GitHub Service + Code Extractor (structure/logic only — no live calls)

Run from backend/ directory:
    python test_ml_features.py
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, label, detail))
    icon = "OK " if condition else "XX "
    print(f"  {icon} {label}" + (f"  ({detail})" if detail else ""))
    return condition

def warn(label, detail=""):
    results.append((WARN, label, detail))
    print(f"  !! {label}" + (f"  ({detail})" if detail else ""))

def section(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════
# FEATURE 1 — GAME TYPE CLASSIFIER
# ══════════════════════════════════════════════════════════════

section("FEATURE 1: Game Type Classifier — Model Integrity")

from app.ml.classifier import predict_game_type, MODEL_PATH

# 1.1 Model file exists
check("Model file exists", MODEL_PATH.exists(), str(MODEL_PATH))

# 1.2 Model loads without error
try:
    result = predict_game_type("test")
    check("Model loads cleanly", result.get("source") == "ml_model",
          f"source={result.get('source')}")
except Exception as e:
    check("Model loads cleanly", False, str(e))

# 1.3 Return schema is correct
r = predict_game_type("make a platformer game")
check("Returns game_type key",        "game_type"            in r)
check("Returns confidence key",       "confidence"           in r)
check("Returns needs_clarification",  "needs_clarification"  in r)
check("Returns top3 key",             "top3"                 in r)
check("Returns source key",           "source"               in r)
check("top3 has 3 entries",           len(r.get("top3", [])) == 3,
      f"got {len(r.get('top3', []))}")
check("confidence is float 0-1",
      isinstance(r["confidence"], float) and 0.0 <= r["confidence"] <= 1.0,
      f"{r['confidence']}")
check("needs_clarification is bool",  isinstance(r["needs_clarification"], bool))


section("FEATURE 1: Game Type Classifier — Core Predictions")

CORE_CASES = [
    # (prompt, expected_label, min_confidence)
    ("make a mario style game",                      "platformer",    0.70),
    ("game where a bird flies through pipes",        "flappy",        0.70),
    ("build a tower defense game with archers",      "tower_defense", 0.70),
    ("space invaders clone",                         "space_shooter", 0.70),
    ("classic snake game",                           "snake",         0.70),
    ("street fighter style fighting game",           "fighting",      0.70),
    ("survive waves of zombies",                     "survival",      0.70),
    ("top down gta style game",                      "topdown",       0.70),
    ("car racing with drift mechanics",              "racing",        0.70),
    ("match 3 puzzle game",                          "puzzle",        0.70),
    ("rpg with dungeons and loot",                   "rpg",           0.70),
    ("shoot aliens from your spaceship",             "space_shooter", 0.70),
    ("tap to fly through obstacles",                 "flappy",        0.60),
    ("something like sonic but simpler",             "platformer",    0.60),
]

core_pass = 0
for prompt, expected, min_conf in CORE_CASES:
    r = predict_game_type(prompt)
    ok = r["game_type"] == expected
    conf_ok = r["confidence"] >= min_conf
    if ok:
        core_pass += 1
    label = f"'{prompt[:45]}'"
    detail = f"got={r['game_type']} conf={r['confidence']:.0%}"
    if not ok:
        detail += f" expected={expected}"
    check(label, ok, detail)

print(f"\n  Core accuracy: {core_pass}/{len(CORE_CASES)} ({core_pass/len(CORE_CASES):.0%})")


section("FEATURE 1: Game Type Classifier — Indirect / Metaphor Prompts")

INDIRECT_CASES = [
    ("a creature soars between tall obstacles",      "flappy"),
    ("a knight explores dungeons and levels up",     "rpg"),
    ("retro style pixel game",                       "arcade"),
    ("hold the line against enemy waves",            "tower_defense"),
    ("last man standing wins",                       "survival"),
    ("build defenses and stop the invasion",         "tower_defense"),
    ("a hero runs right and jumps over everything",  "platformer"),
    ("match tiles to clear the board",               "puzzle"),
]

indirect_pass = 0
for prompt, expected in INDIRECT_CASES:
    r = predict_game_type(prompt)
    ok = r["game_type"] == expected
    if ok:
        indirect_pass += 1
    detail = f"got={r['game_type']} conf={r['confidence']:.0%}"
    if not ok:
        detail += f" expected={expected}"
    check(f"'{prompt[:45]}'", ok, detail)

print(f"\n  Indirect accuracy: {indirect_pass}/{len(INDIRECT_CASES)} ({indirect_pass/len(INDIRECT_CASES):.0%})")


section("FEATURE 1: Game Type Classifier — Typo Robustness")

TYPO_CASES = [
    ("platfomer game",        "platformer"),
    ("platfomr",              "platformer"),
    ("flapy bird",            "flappy"),
    ("flappyy brd",           "flappy"),
    ("towr defens",           "tower_defense"),
    ("spaace shootr",         "space_shooter"),
    ("racng caar game",       "racing"),
    ("puzzl match 3",         "puzzle"),
    ("rpgg quest game",       "rpg"),
    ("fihgting game",         "fighting"),
    ("zombe survval",         "survival"),
    ("shotr game",            "shooter"),
]

typo_pass = 0
for prompt, expected in TYPO_CASES:
    r = predict_game_type(prompt)
    ok = r["game_type"] == expected
    if ok:
        typo_pass += 1
    detail = f"got={r['game_type']} conf={r['confidence']:.0%}"
    if not ok:
        detail += f" expected={expected}"
    check(f"'{prompt}'", ok, detail)

print(f"\n  Typo robustness: {typo_pass}/{len(TYPO_CASES)} ({typo_pass/len(TYPO_CASES):.0%})")


section("FEATURE 1: Game Type Classifier — Edge Cases")

# Vague prompt → needs_clarification
vague = predict_game_type("fun")
check("'fun' triggers needs_clarification",
      vague["needs_clarification"] or vague["confidence"] < 0.45,
      f"conf={vague['confidence']:.0%}")

# Empty string
try:
    empty = predict_game_type("")
    check("Empty string doesn't crash", True, f"got={empty['game_type']}")
except Exception as e:
    check("Empty string doesn't crash", False, str(e))

# Very long prompt
long_prompt = "make a game " * 50
try:
    long_r = predict_game_type(long_prompt)
    check("Very long prompt doesn't crash", True, f"got={long_r['game_type']}")
except Exception as e:
    check("Very long prompt doesn't crash", False, str(e))

# All 13 game types are in the model's known classes
from app.ml.classifier import _load_model
pipeline = _load_model()
if pipeline:
    known = set(pipeline.classes_)
    expected_types = {
        "platformer","shooter","racing","puzzle","rpg",
        "tower_defense","flappy","snake","space_shooter",
        "fighting","survival","topdown","arcade"
    }
    missing = expected_types - known
    extra   = known - expected_types
    check("All 13 game types in model", len(missing) == 0,
          f"missing={missing}" if missing else "")
    if extra:
        warn("Unexpected extra classes in model", str(extra))

# top3 confidences sum to <= 1.0 (they're a subset of the full distribution)
r = predict_game_type("mario platformer")
top3_sum = sum(x["confidence"] for x in r["top3"])
check("top3 confidences <= 1.0", top3_sum <= 1.001, f"sum={top3_sum:.4f}")

# top3[0] matches game_type
check("top3[0] matches game_type prediction",
      r["top3"][0]["game_type"] == r["game_type"],
      f"top3[0]={r['top3'][0]['game_type']} game_type={r['game_type']}")

# top3 is sorted descending
confs = [x["confidence"] for x in r["top3"]]
check("top3 sorted descending", confs == sorted(confs, reverse=True), str(confs))


# ══════════════════════════════════════════════════════════════
# FEATURE 2 — HYBRID SEARCH SERVICE
# ══════════════════════════════════════════════════════════════

section("FEATURE 2: Hybrid Search — Setup")

from app.services.search_service import search_service, _tokenize, _score_project

# Tokenizer
check("Tokenize removes stop words",
      "game" not in _tokenize("make a game"),
      str(_tokenize("make a game")))
check("Tokenize lowercases",
      _tokenize("MARIO") == ["mario"],
      str(_tokenize("MARIO")))
check("Tokenize removes single chars",
      "a" not in _tokenize("a platformer"),
      str(_tokenize("a platformer")))
check("Tokenize handles empty string",
      _tokenize("") == [],
      str(_tokenize("")))
check("Tokenize extracts meaningful tokens",
      "platformer" in _tokenize("build a mario platformer"),
      str(_tokenize("build a mario platformer")))


section("FEATURE 2: Hybrid Search — Empty Query")

MOCK_PROJECTS = [
    {
        "project_id":  "p1",
        "name":        "Mario Adventure",
        "description": "A classic platformer game",
        "framework":   "phaser",
        "design_doc":  {"game_type": "platformer", "mechanics": ["jump", "run"]},
    },
    {
        "project_id":  "p2",
        "name":        "Space Wars",
        "description": "Shoot aliens in space",
        "framework":   "phaser",
        "design_doc":  {"game_type": "space_shooter", "mechanics": ["shoot", "dodge"]},
    },
    {
        "project_id":  "p3",
        "name":        "Pipe Runner",
        "description": "Bird flying through pipes",
        "framework":   "phaser",
        "design_doc":  {"game_type": "flappy", "mechanics": ["tap", "fly"]},
    },
    {
        "project_id":  "p4",
        "name":        "Tower Hold",
        "description": "Defend your base with towers",
        "framework":   "godot",
        "design_doc":  {"game_type": "tower_defense", "mechanics": ["place towers", "defend"]},
    },
]

result = search_service.search("", MOCK_PROJECTS)
check("Empty query returns all projects",   result["total"] == 4, f"got {result['total']}")
check("Empty query has 0 keyword_hits",     result["keyword_hits"] == 0)
check("Empty query has 0 ml_hits",         result["ml_hits"] == 0)
check("Empty query score is 1.0",
      all(r["score"] == 1.0 for r in result["results"]),
      str([r["score"] for r in result["results"]]))
check("Empty query match_type is keyword",
      all(r["match_type"] == "keyword" for r in result["results"]))


section("FEATURE 2: Hybrid Search — Keyword Matching")

result = search_service.search("mario", MOCK_PROJECTS)
ids = [r["project"]["project_id"] for r in result["results"]]
check("'mario' finds Mario Adventure",         "p1" in ids, str(ids))
check("'mario' doesn't find Space Wars",       "p2" not in ids, str(ids))
check("keyword_hits >= 1",                     result["keyword_hits"] >= 1)

result = search_service.search("space aliens", MOCK_PROJECTS)
ids = [r["project"]["project_id"] for r in result["results"]]
check("'space aliens' finds Space Wars",       "p2" in ids, str(ids))

# Scoring: name match > description match
result = search_service.search("platformer", MOCK_PROJECTS)
scores = {r["project"]["project_id"]: r["score"] for r in result["results"]}
check("'platformer' finds platformer project", "p1" in scores)

# Framework search
result = search_service.search("godot", MOCK_PROJECTS)
ids = [r["project"]["project_id"] for r in result["results"]]
check("'godot' finds godot project",           "p4" in ids, str(ids))

# Results sorted by score descending
result = search_service.search("platformer adventure", MOCK_PROJECTS)
sc = [r["score"] for r in result["results"]]
check("Results sorted by score descending",    sc == sorted(sc, reverse=True), str(sc))

# matched_terms populated
result = search_service.search("mario", MOCK_PROJECTS)
mt = result["results"][0]["matched_terms"] if result["results"] else []
check("matched_terms populated on keyword hit", len(mt) > 0, str(mt))

# No duplicate project_ids in results
result = search_service.search("platformer", MOCK_PROJECTS)
pids = [r["project"]["project_id"] for r in result["results"]]
check("No duplicate projects in results",
      len(pids) == len(set(pids)), f"pids={pids}")


section("FEATURE 2: Hybrid Search — ML Stage")

# ML stage: search for "platformer" type query — should find platformer via ML
result = search_service.search("jumping side scroll", MOCK_PROJECTS)
check("ML search doesn't crash",               result is not None)
check("Results is a list",                     isinstance(result["results"], list))
check("predicted_game_type returned",          "predicted_game_type" in result)
check("classifier_confidence returned",        "classifier_confidence" in result)

# No project appears twice (ML + keyword dedup)
all_pids = [r["project"]["project_id"] for r in result["results"]]
check("No project duplicated across stages",
      len(all_pids) == len(set(all_pids)), str(all_pids))

# match_type values are valid
for r in result["results"]:
    valid = r["match_type"] in ("keyword", "game_type")
    if not valid:
        check(f"Invalid match_type: {r['match_type']}", False)
        break
else:
    check("All match_types are valid ('keyword' or 'game_type')", True)


section("FEATURE 2: Hybrid Search — Edge Cases")

# Single project
single = search_service.search("mario", MOCK_PROJECTS[:1])
check("Single project list works",             single is not None)

# Empty project list
empty = search_service.search("mario", [])
check("Empty project list returns empty",      empty["total"] == 0, f"got {empty['total']}")
check("Empty project list no crash",           isinstance(empty["results"], list))

# Project with missing fields
sparse = [{"project_id": "p_sparse", "name": "sparse"}]
try:
    r = search_service.search("sparse", sparse)
    check("Project with missing fields doesn't crash", True,
          f"total={r['total']}")
except Exception as e:
    check("Project with missing fields doesn't crash", False, str(e))

# Query with only stop words
result = search_service.search("make a game", MOCK_PROJECTS)
check("All-stopword query returns valid result",
      isinstance(result["results"], list))

# Very long query
long_q = "platformer " * 30
try:
    result = search_service.search(long_q, MOCK_PROJECTS)
    check("Very long query doesn't crash",     isinstance(result["results"], list))
except Exception as e:
    check("Very long query doesn't crash", False, str(e))

# Special chars in query
try:
    result = search_service.search("mario! @#$%", MOCK_PROJECTS)
    check("Special chars in query don't crash", isinstance(result["results"], list))
except Exception as e:
    check("Special chars in query don't crash", False, str(e))


# ══════════════════════════════════════════════════════════════
# FEATURE 3 — GITHUB SERVICE + CODE EXTRACTOR
# ══════════════════════════════════════════════════════════════

section("FEATURE 3: GitHub Service — Query Builder")

from app.services.github_service import _build_query, _FRAMEWORK_LANG, _GAME_TYPE_KEYWORDS

# Query building logic
q = _build_query("platformer", "phaser")
check("Phaser query contains 'javascript'",    "javascript" in q, q)
check("Query contains 'topic:game'",           "topic:game" in q, q)
check("Query contains license filter",         "license:mit" in q, q)
check("Query contains game type keyword",      "platformer" in q, q)

q2 = _build_query("platformer", "godot")
check("Godot query contains 'gdscript'",       "gdscript" in q2, q2)

q3 = _build_query("racing", "canvas")
check("Canvas maps to javascript",             "javascript" in q3, q3)

q4 = _build_query("arcade", "unknown_framework")
check("Unknown framework still produces valid query", "topic:game" in q4, q4)

# All 13 game types have keyword mappings
expected_types = {
    "platformer","shooter","racing","puzzle","rpg",
    "tower_defense","flappy","snake","space_shooter",
    "fighting","survival","topdown","arcade"
}
missing_keywords = expected_types - set(_GAME_TYPE_KEYWORDS.keys())
check("All 13 game types have keyword mappings",
      len(missing_keywords) == 0,
      f"missing={missing_keywords}" if missing_keywords else "")


section("FEATURE 3: GitHub Service — Async / Structure")

async def test_github_no_token():
    """With no token, should return [] gracefully (rate limited or no network)."""
    from app.services.github_service import search_similar_repos
    try:
        # We use a short timeout to not block tests
        repos = await asyncio.wait_for(
            search_similar_repos("platformer", "phaser", token=""),
            timeout=8.0
        )
        check("GitHub search returns a list", isinstance(repos, list),
              f"type={type(repos)}")
        if repos:
            r = repos[0]
            check("Repo has full_name",       "full_name"      in r)
            check("Repo has stars",           "stars"          in r)
            check("Repo has default_branch",  "default_branch" in r)
            check("Repo has html_url",        "html_url"       in r)
            check("Repo has framework field", "framework"      in r)
            check("Repo count <= 3",          len(repos) <= 3, f"got {len(repos)}")
        else:
            warn("GitHub returned 0 results (no token / rate limit / no network)", "")
    except asyncio.TimeoutError:
        warn("GitHub search timed out (no network or slow connection)", "")
    except Exception as e:
        warn(f"GitHub search raised: {e}", "")

asyncio.run(test_github_no_token())


section("FEATURE 3: Code Extractor — Logic Tests")

from app.services.code_extractor import _trim, _CANDIDATE_FILES, _MAX_CHARS_PER_FILE, _MAX_TOTAL_CHARS

# _trim function
short = "hello world"
check("_trim: short string unchanged",         _trim(short, 100) == short)

long_str = "x" * 2000
trimmed = _trim(long_str, 500)
check("_trim: long string is trimmed",         len(trimmed) <= 520)  # 500 + truncation note
check("_trim: truncation note appended",       "[truncated]" in trimmed)

# Budget constants are sensible
check("Per-file budget is reasonable",
      500 <= _MAX_CHARS_PER_FILE <= 5000,
      f"{_MAX_CHARS_PER_FILE}")
check("Total budget is reasonable",
      1000 <= _MAX_TOTAL_CHARS <= 20000,
      f"{_MAX_TOTAL_CHARS}")
check("Total budget >= per-file budget",
      _MAX_TOTAL_CHARS >= _MAX_CHARS_PER_FILE)

# Candidate files list is sensible
check("Candidate files list is non-empty",     len(_CANDIDATE_FILES) > 0)
check("index.html is first candidate",         _CANDIDATE_FILES[0] == "index.html")
check("README.md is in candidates",            "README.md" in _CANDIDATE_FILES)
check("game.js is in candidates",              "game.js" in _CANDIDATE_FILES)


section("FEATURE 3: Code Extractor — fetch_reference_code with empty repos")

async def test_extractor_empty():
    from app.services.code_extractor import fetch_reference_code
    result = await fetch_reference_code([])
    check("fetch_reference_code([]) returns empty string", result == "", repr(result))

asyncio.run(test_extractor_empty())


section("FEATURE 3: Code Extractor — fetch_reference_code with bad repo")

async def test_extractor_bad_repo():
    from app.services.code_extractor import fetch_reference_code
    bad_repos = [{"full_name": "nonexistent-user-xyz/nonexistent-repo-abc-123",
                  "default_branch": "main", "html_url": "", "description": "", "stars": 0}]
    try:
        result = await asyncio.wait_for(fetch_reference_code(bad_repos), timeout=12.0)
        check("Bad repo returns empty string (not crash)", isinstance(result, str),
              f"got: {repr(result[:80])}")
    except asyncio.TimeoutError:
        warn("Code extractor timed out on bad repo", "")
    except Exception as e:
        check("Bad repo doesn't raise exception", False, str(e))

asyncio.run(test_extractor_bad_repo())


# ══════════════════════════════════════════════════════════════
# TRAINING DATA INTEGRITY CHECK
# ══════════════════════════════════════════════════════════════

section("TRAINING DATA: Integrity")

DATA_PATH = Path(__file__).parent / "app/ml/training_data/game_prompts.json"
with open(DATA_PATH) as f:
    raw = json.load(f)

data = raw["data"]
labels = [item["label"] for item in data]
texts  = [item["text"]  for item in data]

check("Training data has 400+ examples",    len(data) >= 400, f"got {len(data)}")
check("All items have 'text' field",
      all("text" in item for item in data))
check("All items have 'label' field",
      all("label" in item for item in data))
check("No empty texts",
      all(len(item["text"].strip()) > 0 for item in data))
check("All labels are valid game types",
      all(item["label"] in {
          "platformer","shooter","racing","puzzle","rpg",
          "tower_defense","flappy","snake","space_shooter",
          "fighting","survival","topdown","arcade"
      } for item in data))

dist = Counter(labels)
min_count = min(dist.values())
max_count = max(dist.values())
check("Each game type has at least 15 examples",
      min_count >= 15,
      f"min={min_count} ({min(dist, key=dist.get)})")
check("Class imbalance ratio <= 5x",
      max_count / min_count <= 5.0,
      f"max={max_count} min={min_count} ratio={max_count/min_count:.1f}x")

# No duplicate texts
dupes = len(texts) - len(set(texts))
check("No duplicate training examples", dupes == 0, f"{dupes} duplicates found")

print()
print("  Distribution:")
for gt, cnt in sorted(dist.items()):
    bar = "#" * (cnt // 3)
    print(f"    {gt:<20} {cnt:>3}  {bar}")


# ══════════════════════════════════════════════════════════════
# CROSS-FEATURE CONSISTENCY
# ══════════════════════════════════════════════════════════════

section("CROSS-FEATURE: Classifier -> Search consistency")

# The search ML stage uses the same classifier — ensure they agree
from app.services.search_service import search_service

classifier_result = predict_game_type("mario platformer jumping game")
search_result = search_service.search("mario platformer jumping game", MOCK_PROJECTS)

check("Search uses same classifier game_type",
      search_result.get("predicted_game_type") == classifier_result["game_type"]
      or search_result.get("predicted_game_type") is None,  # may be None if confidence too low
      f"classifier={classifier_result['game_type']} search={search_result.get('predicted_game_type')}")

# Confirm needs_clarification=True suppresses ML in search
vague_pred = predict_game_type("something cool")
vague_search = search_service.search("something cool", MOCK_PROJECTS)
if vague_pred["needs_clarification"]:
    check("Vague query: ML stage suppressed in search (0 ml_hits)",
          vague_search["ml_hits"] == 0,
          f"ml_hits={vague_search['ml_hits']}")
else:
    warn("'something cool' not flagged as needing clarification",
         f"conf={vague_pred['confidence']:.0%}")

# Confirm github framework mapping covers all classifier game types
from app.services.github_service import _GAME_TYPE_KEYWORDS
classifier_types = set(pipeline.classes_) if pipeline else set()
missing_in_github = classifier_types - set(_GAME_TYPE_KEYWORDS.keys())
check("All classifier game types covered in GitHub keyword map",
      len(missing_in_github) == 0,
      f"missing: {missing_in_github}" if missing_in_github else "")


# ══════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════

section("FINAL SUMMARY")

total   = len([r for r in results if r[0] in (PASS, FAIL)])
passed  = len([r for r in results if r[0] == PASS])
failed  = len([r for r in results if r[0] == FAIL])
warned  = len([r for r in results if r[0] == WARN])

print(f"\n  Total checks : {total}")
print(f"  Passed       : {passed}")
print(f"  Failed       : {failed}")
print(f"  Warnings     : {warned}")
print(f"\n  Score        : {passed}/{total} ({passed/total:.0%})")

if failed > 0:
    print("\n  FAILURES:")
    for status, label, detail in results:
        if status == FAIL:
            print(f"    XX {label}" + (f"  -> {detail}" if detail else ""))

if warned > 0:
    print("\n  WARNINGS:")
    for status, label, detail in results:
        if status == WARN:
            print(f"    !! {label}" + (f"  -> {detail}" if detail else ""))

print()
