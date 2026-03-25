"""
Live API test — tests Gemini generation + GitHub enrichment end-to-end.
Run from backend/: python test_api_live.py
"""
import asyncio
import sys
import os

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

SEP  = "-" * 60
SEP2 = "=" * 60


async def test_github_search():
    from app.services.github_service import search_similar_repos, _build_query

    print(SEP2)
    print("  PART 1 -- GITHUB REPO SEARCH")
    print(SEP2)

    test_cases = [
        ("platformer", "phaser"),
        ("snake",      "vanilla"),
        ("survival",   "phaser"),
        ("puzzle",     "phaser"),
    ]

    for game_type, framework in test_cases:
        q = _build_query(game_type, framework)
        print(f"  Query: {q}")
        repos = await search_similar_repos(game_type, framework)
        if repos:
            for r in repos:
                print(f"    [{r['stars']:>5} stars] {r['full_name']}")
                print(f"             {r['description'][:80]}")
        else:
            print("    (no results / rate limited / no token)")
        print()


async def test_github_code_extract():
    from app.services.github_service import search_similar_repos
    from app.services.code_extractor import fetch_reference_code

    print(SEP2)
    print("  PART 2 -- GITHUB CODE EXTRACTION")
    print(SEP2)

    repos = await search_similar_repos("platformer", "phaser")
    if not repos:
        print("  No repos found — skipping code extract test")
        return

    print(f"  Fetching code from: {repos[0]['full_name']}")
    code = await fetch_reference_code(repos)
    if code:
        lines = code.split("\n")
        print(f"  Extracted {len(code)} chars  ({len(lines)} lines)")
        print()
        print("  First 30 lines:")
        for line in lines[:30]:
            print(f"    {line}")
        print("  ...")
    else:
        print("  No code extracted (files not found in repo)")
    print()


async def test_gemini_direct():
    from app.services.ai_providers import provider_manager

    print(SEP2)
    print("  PART 3 -- GEMINI API DIRECT CALL")
    print(SEP2)

    prompt = (
        "Return a one-sentence description of a snake game. "
        "No JSON, just plain text."
    )
    print(f"  Prompt: '{prompt}'")
    print()

    try:
        result = await provider_manager.generate(prompt, temperature=0.5)
        print(f"  Provider : {result.usage.provider}")
        print(f"  Model    : {result.usage.model}")
        print(f"  Tokens   : {result.usage.total_tokens}")
        print(f"  Response : {result.text[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


async def test_design_generation():
    from app.services.ai_orchestrator import AIOrchestrator

    print(SEP2)
    print("  PART 4 -- DESIGN AGENT (Gemini game design doc)")
    print(SEP2)

    orchestrator = AIOrchestrator()

    prompts = [
        "make a snake game with power ups and walls",
        "build a tower defense with archers and cannons",
    ]

    for prompt in prompts:
        print(f"  Prompt: '{prompt}'")
        try:
            result = await orchestrator.generate_design(prompt)
            d = result.payload
            print(f"  game_type : {d.get('game_type')}")
            print(f"  summary   : {str(d.get('summary',''))[:120]}")
            print(f"  mechanics : {d.get('mechanics', [])}")
            print(f"  entities  : {[e.get('name') for e in d.get('entities', [])]}")
            print(f"  tokens    : {result.usage.total_tokens}")
        except Exception as e:
            print(f"  ERROR: {e}")
        print()


async def test_full_generation():
    from app.services.ai_orchestrator import AIOrchestrator

    print(SEP2)
    print("  PART 5 -- FULL CODE GENERATION (design + GitHub + agents)")
    print(SEP2)

    orchestrator = AIOrchestrator()
    prompt = "classic snake game with increasing speed"

    print(f"  Prompt  : '{prompt}'")
    print(f"  Note    : This calls Gemini multiple times + tries GitHub for reference code")
    print()

    try:
        result = await orchestrator.generate_code(prompt)
        payload = result.payload
        files   = payload.get("files", {})

        print(f"  Status          : {payload.get('status', 'unknown')}")
        print(f"  Files generated : {list(files.keys())}")
        print(f"  Total tokens    : {result.usage.total_tokens}")
        print()

        if "index.html" in files:
            html = files["index.html"]
            print(f"  index.html      : {len(html)} chars")
            print(f"  First 10 lines  :")
            for line in html.split("\n")[:10]:
                print(f"    {line}")
            print("    ...")

            # Check what it uses
            uses_phaser = "phaser" in html.lower()
            uses_canvas = "<canvas" in html.lower()
            uses_github_ref = "raw.githubusercontent" in html.lower() or "github.com" in html.lower()
            print()
            print(f"  Uses Phaser.js  : {uses_phaser}")
            print(f"  Uses <canvas>   : {uses_canvas}")
            print(f"  Contains GitHub URL in output: {uses_github_ref}")

    except Exception as e:
        import traceback
        print(f"  ERROR: {e}")
        traceback.print_exc()
    print()


async def test_github_flow_trace():
    """Show exactly how GitHub enrichment feeds into the Gemini prompt."""
    from app.services.github_service import search_similar_repos
    from app.services.code_extractor import fetch_reference_code

    print(SEP2)
    print("  PART 6 -- GITHUB -> PROMPT FLOW TRACE")
    print(SEP2)
    print("  This shows HOW GitHub code is used (injected into Gemini prompt context)")
    print()

    repos = await search_similar_repos("snake", "phaser")
    if not repos:
        print("  No GitHub repos found (rate limit or no token).")
        print("  When GITHUB_TOKEN is set, it finds up to 3 MIT/Apache repos,")
        print("  downloads their index.html / game.js (capped at 4000 chars total),")
        print("  and prepends it to the Gemini code-generation prompt as reference.")
        print()
        return

    code = await fetch_reference_code(repos)
    print(f"  Found {len(repos)} repos. Reference code extracted: {len(code)} chars")
    print()
    print("  How it's used in the Gemini prompt:")
    print("  ┌──────────────────────────────────────┐")
    print("  │  SYSTEM: You are an expert game dev  │")
    print("  │  ...                                 │")
    print("  │  REFERENCE CODE FROM GITHUB:         │")
    print("  │  [up to 4000 chars from real repos]  │  <-- GitHub code injected here")
    print("  │                                      │")
    print("  │  USER REQUEST: make a snake game     │")
    print("  └──────────────────────────────────────┘")
    print()
    print("  The AI uses this as style/pattern reference — NOT copy-paste.")
    print("  Only MIT/Apache-2.0 licensed repos are used.")
    print()
    if code:
        print("  Sample reference (first 400 chars):")
        print(code[:400])
    print()


if __name__ == "__main__":
    print()
    print(SEP2)
    print("  ForgeAI -- Live API + GitHub Integration Test")
    print(SEP2)
    print()

    asyncio.run(test_github_search())
    asyncio.run(test_github_code_extract())
    asyncio.run(test_gemini_direct())
    asyncio.run(test_design_generation())
    asyncio.run(test_github_flow_trace())

    print()
    print("  Skipping Part 5 (full code gen) -- uses many tokens.")
    print("  To run it: uncomment asyncio.run(test_full_generation()) below")
    # asyncio.run(test_full_generation())

    print()
    print(SEP2)
    print("  Done.")
    print(SEP2)
