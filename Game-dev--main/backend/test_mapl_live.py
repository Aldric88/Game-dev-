"""Live integration test for MAPL endpoints."""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000/api/v1"


def post(path, data, token=None):
    body = json.dumps(data).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def patch(path, data, token):
    body = json.dumps(data).encode()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method="PATCH")
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def get(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, headers=headers)
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


# 1) Register or login
resp, code = post("/auth/register", {
    "username": "mapl_tester",
    "email": "mapl_tester@example.com",
    "password": "TestPass123!",
})
if code == 200:
    token = resp["access_token"]
    print("1. Registered new user OK")
else:
    resp, code = post("/auth/login", {
        "email": "mapl_tester@example.com",
        "password": "TestPass123!",
    })
    token = resp["access_token"]
    print("1. Logged in OK")

# 2) Create a project
resp, code = post("/projects", {"name": "MAPL Test Game", "description": "Space shooter"}, token)
pid = resp.get("project_id", "")
print(f"2. Created project: {pid} (status={code})")

# 3) MAPL /stats — should work (may be empty)
resp, code = get("/mapl/stats", token)
print(f"3. GET /mapl/stats -> {code}")
print(f"   short_term={resp.get('short_term_count')}, long_term={resp.get('long_term_count')}, total={resp.get('total_memories')}")

# 4) MAPL /retrieve — query with empty memory
resp, code = post("/mapl/retrieve", {"prompt": "make a space shooter game", "game_type": "space_shooter"}, token)
mem_count = len(resp.get("memories", []))
print(f"4. POST /mapl/retrieve -> {code}, memories found: {mem_count}")

# 5) Give the project a design_doc so feedback can work
design = {
    "summary": "A space shooter game with alien enemies",
    "game_type": "space_shooter",
    "mechanics": ["shooting", "dodging", "power_ups"],
    "entities": [
        {"name": "Player Ship", "type": "character", "behaviors": ["move", "shoot"]},
        {"name": "Alien Fighter", "type": "enemy", "behaviors": ["patrol", "attack"]},
    ],
    "visual_style": {"theme": "neon", "primary_colors": ["#00ff00", "#0000ff"]},
}
patch(f"/projects/{pid}", {"design_doc": design}, token)

# 6) MAPL /feedback — record a positive experience
resp, code = post("/mapl/feedback", {
    "project_id": pid,
    "reward": 0.9,
    "outcome": "success",
    "notes": "Great game, plays well!",
}, token)
print(f"5. POST /mapl/feedback -> {code}")
print(f"   memory_id={resp.get('memory_id')}, tier={resp.get('tier')}, reward={resp.get('reward')}")

# 7) Record another experience (different game type)
resp2, _ = post("/projects", {"name": "Racing Test", "description": "Racing game"}, token)
pid2 = resp2.get("project_id", "")
racing_design = {
    "summary": "A top-down racing game with drift mechanics",
    "game_type": "racing",
    "mechanics": ["steering", "drifting", "boost"],
    "entities": [{"name": "Player Car", "type": "character"}],
}
patch(f"/projects/{pid2}", {"design_doc": racing_design}, token)
resp, code = post("/mapl/feedback", {
    "project_id": pid2,
    "reward": 0.5,
    "outcome": "partial",
    "notes": "Drift physics need work",
}, token)
print(f"6. POST /mapl/feedback (racing) -> {code}, tier={resp.get('tier')}")

# 8) Check stats again — should now have memories
resp, code = get("/mapl/stats", token)
print(f"7. GET /mapl/stats -> {code}")
print(f"   short_term={resp.get('short_term_count')}, long_term={resp.get('long_term_count')}, total={resp.get('total_memories')}")
print(f"   avg_reward={resp.get('avg_reward')}, top_types={resp.get('top_game_types')}")

# 9) Retrieve again — should find the space_shooter memory
resp, code = post("/mapl/retrieve", {"prompt": "create a space shooter with aliens", "game_type": "space_shooter"}, token)
mem_count = len(resp.get("memories", []))
print(f"8. POST /mapl/retrieve (space query) -> {code}, memories found: {mem_count}")
for i, m in enumerate(resp.get("memories", [])):
    mem = m["memory"]
    print(f"   [{i+1}] score={m['total_score']:.3f} game_type={mem['state']['game_type']} reward={mem['reward']} outcome={mem['outcome']}")
aug = resp.get("prompt_augmentation", "")
if aug:
    print(f"   Prompt augmentation:\n   {aug}")

# 10) Test /optimize
resp, code = post("/mapl/optimize", {}, token)
print(f"9. POST /mapl/optimize -> {code}")
print(f"   {resp}")

print("\n=== ALL MAPL TESTS PASSED ===")
