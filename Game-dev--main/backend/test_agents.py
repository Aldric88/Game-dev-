"""
Standalone agent integration test.
Run from the backend/ directory:
    python test_agents.py
No API keys needed — forces AI_PROVIDER=stub and mocks S3.
"""
import asyncio
import os
import sys

# Force stub provider before any app imports
os.environ["AI_PROVIDER"] = "stub"
sys.path.insert(0, os.path.dirname(__file__))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    tag = PASS if condition else FAIL
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    _results.append((name, condition))


# ── Imports ────────────────────────────────────────────────────────────────────
try:
    from app.agents.base_agent import BaseAgent
    from app.agents.asset_agent import AssetAgent, asset_agent
    from app.agents.script_agent import ScriptAgent, script_agent
    from app.agents.scene_agent import SceneAgent, scene_agent
    from app.services.ai_orchestrator import AIOrchestrator
    from app.services.ai_providers import provider_manager
    import app.services.s3_storage as s3_mod
    print("  [imports OK]")
except Exception as e:
    print(f"  [{FAIL}] Import error: {e}")
    sys.exit(1)


# ── 1. BaseAgent.extract_json ──────────────────────────────────────────────────
def test_extract_json():
    print("\n[1] BaseAgent.extract_json")
    agent = BaseAgent()

    # Plain JSON
    result = agent.extract_json('{"key": "value"}')
    check("plain JSON", result == {"key": "value"})

    # Markdown fenced
    result = agent.extract_json('```json\n{"a": 1}\n```')
    check("markdown fenced", result == {"a": 1})

    # Embedded JSON
    result = agent.extract_json('some text {"x": 42} more text')
    check("embedded JSON", result.get("x") == 42)

    # Invalid → empty dict
    result = agent.extract_json("not json at all")
    check("invalid -> empty dict", result == {})


# ── 2. AssetAgent ──────────────────────────────────────────────────────────────
async def test_asset_agent():
    print("\n[2] AssetAgent")
    entity = {"name": "Player", "type": "character"}
    design = {"game_type": "platformer"}

    result = await asset_agent.run(entity, design)
    check("returns dict", isinstance(result, dict))
    check("has png_b64", bool(result.get("png_b64")))
    check("has width", isinstance(result.get("width"), int))
    check("has height", isinstance(result.get("height"), int))
    check("has spec", isinstance(result.get("spec"), dict))

    # Tileset
    tileset = await asset_agent.generate_tileset(design)
    check("tileset is base64 string", isinstance(tileset, str) and len(tileset) > 10)

    # Background
    bg = await asset_agent.generate_background(design)
    check("background is base64 string", isinstance(bg, str) and len(bg) > 10)

    # Enemy entity
    enemy_result = await asset_agent.run({"name": "Enemy", "type": "enemy"}, design)
    check("enemy sprite generated", bool(enemy_result.get("png_b64")))

    # Collectible
    coin_result = await asset_agent.run({"name": "Coin", "type": "collectible"}, design)
    check("coin sprite generated", bool(coin_result.get("png_b64")))


# ── 3. ScriptAgent ─────────────────────────────────────────────────────────────
async def test_script_agent():
    print("\n[3] ScriptAgent")
    design = {"game_type": "platformer", "mechanics": ["jump", "gravity"]}

    player_script = await script_agent.run({"name": "Player", "type": "character", "behaviors": ["movement"]}, design)
    check("player script is string", isinstance(player_script, str))
    check("player extends something", player_script.strip().startswith("extends"))

    enemy_script = await script_agent.run({"name": "Enemy", "type": "enemy", "behaviors": ["patrol"]}, design)
    check("enemy script extends", enemy_script.strip().startswith("extends"))

    coin_script = await script_agent.run({"name": "Coin", "type": "collectible", "behaviors": []}, design)
    check("coin script extends", coin_script.strip().startswith("extends"))

    # Fence stripping
    agent = ScriptAgent()
    stripped = agent._strip_fences("```gdscript\nextends Node2D\n\nfunc _ready():\n\tpass\n```")
    check("strips gdscript fences", stripped.startswith("extends"))


# ── 4. SceneAgent ──────────────────────────────────────────────────────────────
async def test_scene_agent():
    print("\n[4] SceneAgent")
    design = {"game_type": "platformer", "mechanics": ["jump"]}

    tscn = await scene_agent.run({"name": "Player", "type": "character"}, design)
    check("tscn is string", isinstance(tscn, str))
    check("tscn has [gd_scene]", "[gd_scene" in tscn)
    check("tscn has [node", "[node" in tscn)

    enemy_tscn = await scene_agent.run({"name": "Enemy", "type": "enemy"}, design)
    check("enemy tscn valid", "[gd_scene" in enemy_tscn or "[node" in enemy_tscn)

    coin_tscn = await scene_agent.run({"name": "Coin", "type": "collectible"}, design)
    check("coin tscn valid", "[gd_scene" in coin_tscn or "[node" in coin_tscn)


# ── 5. AIOrchestrator.generate_design ─────────────────────────────────────────
async def test_orchestrator_design():
    print("\n[5] AIOrchestrator.generate_design")
    orch = AIOrchestrator()
    result = await orch.generate_design("make a platformer with coins and enemies")
    check("returns OrchestratorResult", hasattr(result, "payload"))
    check("payload has game_type", "game_type" in result.payload)
    check("payload has entities", "entities" in result.payload)
    check("summary is string", isinstance(result.summary, str))


# ── 6. AIOrchestrator.generate_complete_game (S3 mocked) ──────────────────────
async def test_orchestrator_complete():
    print("\n[6] AIOrchestrator.generate_complete_game (S3 mocked)")

    # Mock S3 so no AWS needed
    class MockS3:
        async def upload_file_content(self, *a, **kw):
            return {"url": "https://mock-s3/file"}
        async def upload_bytes_content(self, *a, **kw):
            return {"url": "https://mock-s3/bytes"}
        async def upload_project_files(self, *a, **kw):
            return {}

    s3_mod.s3_storage = MockS3()

    # Re-import orchestrator module to pick up mocked s3_storage
    import importlib
    import app.services.ai_orchestrator as orch_mod
    orch_mod.s3_storage = MockS3()

    orch = AIOrchestrator()
    result = await orch.generate_complete_game(
        prompt="make a simple platformer",
        username="testuser",
        project_name="testproject",
        project_id="proj-001",
        realtime=None,
    )

    check("result has status", bool(result.status))
    check("status is complete or partial", result.status in ("complete", "partial"))
    check("has entities in stats", result.stats.get("entities", 0) >= 1)
    check("has scripts", result.stats.get("scripts", 0) >= 1)
    check("has scenes", result.stats.get("scenes", 0) >= 1)
    check("has assets", result.stats.get("assets", 0) >= 1)
    check("file_urls populated", len(result.file_urls) > 0)

    if result.errors:
        print(f"    non-fatal errors: {result.errors}")


# ── 7. Agent parallel execution ───────────────────────────────────────────────
async def test_parallel_execution():
    print("\n[7] Parallel execution (gather)")
    design = {"game_type": "arcade", "mechanics": ["collect"]}
    entities = [
        {"name": "Player", "type": "character", "behaviors": ["movement"]},
        {"name": "Coin", "type": "collectible", "behaviors": []},
        {"name": "Enemy", "type": "enemy", "behaviors": ["patrol"]},
    ]

    scripts = await asyncio.gather(*[script_agent.run(e, design) for e in entities])
    check("all 3 scripts returned", len(scripts) == 3)
    check("all scripts start with extends", all(s.startswith("extends") for s in scripts))

    scenes = await asyncio.gather(*[scene_agent.run(e, design) for e in entities])
    check("all 3 scenes returned", len(scenes) == 3)
    check("all scenes have [node", all("[node" in s for s in scenes))


# ── Runner ────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 55)
    print("  Agent Integration Tests  (stub provider, mock S3)")
    print("=" * 55)

    test_extract_json()
    await test_asset_agent()
    await test_script_agent()
    await test_scene_agent()
    await test_orchestrator_design()
    await test_orchestrator_complete()
    await test_parallel_execution()

    passed = sum(1 for _, ok in _results if ok)
    failed = sum(1 for _, ok in _results if not ok)
    total = len(_results)
    print("\n" + "=" * 55)
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED")
        for name, ok in _results:
            if not ok:
                print(f"    - {name}")
    else:
        print("  — all green")
    print("=" * 55)
    return failed


if __name__ == "__main__":
    failed = asyncio.run(main())
    sys.exit(1 if failed else 0)
