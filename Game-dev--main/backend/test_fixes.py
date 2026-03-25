"""Quick validation of substring matching fixes."""
import py_compile

for f in ['app/agents/script_agent.py', 'app/agents/scene_agent.py', 'app/services/ai_orchestrator.py']:
    py_compile.compile(f, doraise=True)
    print(f"{f} OK")

print()

from app.services.ai_orchestrator import _normalize_entity
from app.agents.script_agent import _fallback_for
from app.agents.scene_agent import SceneAgent

# Orchestrator
bg = _normalize_entity("Background")
gr = _normalize_entity("Ground")
print(f"Orchestrator: Background -> {bg['type']}  Ground -> {gr['type']}")
assert bg["type"] == "environment", f"Expected environment, got {bg['type']}"
assert gr["type"] == "obstacle", f"Expected obstacle, got {gr['type']}"

# Script agent
bg_s = _fallback_for({"name": "Background", "type": "environment"}).strip().split("\n")[0]
gr_s = _fallback_for({"name": "Ground", "type": "environment"}).strip().split("\n")[0]
print(f"ScriptAgent:  Background -> {bg_s}  Ground -> {gr_s}")
assert "Node2D" in bg_s, f"Background should extend Node2D, got {bg_s}"
assert "StaticBody2D" in gr_s, f"Ground should extend StaticBody2D, got {gr_s}"

# Scene agent
sa = SceneAgent()
bg_spec = sa._fallback_spec({"name": "Background", "type": "environment"})
gr_spec = sa._fallback_spec({"name": "Ground", "type": "environment"})
print(f"SceneAgent:   Background -> {bg_spec['node_type']}  Ground -> {gr_spec['node_type']}")
assert bg_spec["node_type"] == "Node2D", f"Background scene should be Node2D, got {bg_spec['node_type']}"
assert gr_spec["node_type"] == "StaticBody2D", f"Ground scene should be StaticBody2D, got {gr_spec['node_type']}"

print("\nALL ASSERTIONS PASSED")
