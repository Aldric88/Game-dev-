"""AI orchestration with provider adapters and deterministic fallback."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from uuid import uuid4
from dataclasses import dataclass, field
from typing import Any

from app.agents.asset_agent import asset_agent
from app.agents.scene_agent import scene_agent
from app.agents.script_agent import _fallback_for as _fallback_script, script_agent
from app.services.ai_providers import ProviderUsage, provider_manager
from app.services.s3_storage import s3_storage

logger = logging.getLogger(__name__)


@dataclass
class GodotGenerateResult:
    design_doc: dict[str, Any] = field(default_factory=dict)
    file_urls: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    status: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class OrchestratorResult:
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    usage: ProviderUsage = field(default_factory=ProviderUsage)


async def _emit(realtime: Any, project_id: str, event: str, payload: Any = None) -> None:
    """Broadcast a WebSocket event; silently no-ops if realtime is None."""
    if realtime is None:
        return
    try:
        await realtime.broadcast(project_id, event, payload)
    except Exception:
        pass


def _sanitize_name(raw: str) -> str:
    """Strip descriptions, special chars, and produce a clean short entity name.

    Examples:
        "Bird: The Player-Controlled Character." → "Bird"
        "Score Text: Displays The Player's Score"  → "Score Text"
        "AI Opponent Car"                          → "Ai Opponent Car"
    """
    import re
    # Strip everything after a colon, period-at-end, or parenthetical
    name = re.split(r"[:\.\(\)\[\]]", raw)[0].strip()
    # Remove any remaining non-alphanumeric characters (except spaces and hyphens)
    name = re.sub(r"[^a-zA-Z0-9 \-]", "", name).strip()
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)
    # Limit to first 3 words max to keep names short
    words = name.split()
    if len(words) > 3:
        name = " ".join(words[:3])
    return name.strip().title() if name else "Entity"


def _normalize_entity(entity: Any) -> dict[str, Any]:
    """Coerce a string or partial dict entity entry to a full descriptor."""
    if isinstance(entity, dict):
        raw_name = entity.get("name", "Entity")
        return {
            "name": _sanitize_name(raw_name),
            "type": entity.get("type", "character"),
            "behaviors": entity.get("behaviors", entity.get("components", ["movement", "physics"])),
        }
    name = _sanitize_name(str(entity))
    lower = name.lower()

    # Extended keyword matching for better entity type inference
    if any(k in lower for k in ("car", "vehicle", "racer", "kart")):
        return {"name": name, "type": "vehicle", "behaviors": ["steering", "acceleration", "drifting"]}
    if any(k in lower for k in ("track", "road", "circuit")):
        return {"name": name, "type": "environment", "behaviors": ["static"]}
    if any(k in lower for k in ("checkpoint", "finish", "flag")):
        return {"name": name, "type": "trigger", "behaviors": ["detection"]}
    if any(k in lower for k in ("boost", "power", "shield", "speed")):
        return {"name": name, "type": "collectible", "behaviors": ["idle", "pickup", "respawn"]}
    if any(k in lower for k in ("score", "hud", "ui", "health", "timer", "display")):
        return {"name": name, "type": "ui", "behaviors": ["display"]}
    # Background MUST be checked before ground/obstacle (substring collision)
    if any(k in lower for k in ("background", "sky", "scenery")):
        return {"name": name, "type": "environment", "behaviors": ["parallax"]}
    if any(k in lower for k in ("pipe", "obstacle", "wall", "platform", "ground")):
        return {"name": name, "type": "obstacle", "behaviors": ["static"]}
    if any(k in lower for k in ("bullet", "projectile", "laser", "missile")):
        return {"name": name, "type": "projectile", "behaviors": ["movement", "damage"]}
    if any(k in lower for k in ("bird", "ship", "plane", "hero", "fighter")):
        return {"name": name, "type": "character", "behaviors": ["movement", "physics"]}
    if any(k in lower for k in ("patrol", "enemy", "boss", "alien", "monster", "horde", "opponent")):
        etype = "enemy"
        behaviors = ["patrol", "chase", "attack"]
    elif any(k in lower for k in ("coin", "collect", "collectible", "gem", "treasure", "potion", "orb")):
        etype = "collectible"
        behaviors = ["idle", "hover"]
    elif any(k in lower for k in ("snake", "food", "grid")):
        etype = "character"
        behaviors = ["grid_movement"]
    else:
        etype = "character"
        behaviors = ["movement", "physics"]
    return {"name": name, "type": etype, "behaviors": behaviors}


def _generate_project_config(game_name: str, game_type: str = "arcade") -> str:
    """Return a valid Godot 4.2 project.godot configuration string."""

    # Add additional input maps for specific game types
    extra_inputs = ""
    if game_type in ("racing", "topdown", "snake", "survival"):
        extra_inputs = """
move_up={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":87,"key_label":0,"unicode":119,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194320,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}
move_down={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":83,"key_label":0,"unicode":115,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194322,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}
shoot={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":90,"key_label":0,"unicode":122,"location":0,"echo":false,"script":null)]
}}"""
    elif game_type in ("shooter", "space_shooter"):
        extra_inputs = """
move_up={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":87,"key_label":0,"unicode":119,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194320,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}
move_down={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":83,"key_label":0,"unicode":115,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194322,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}
shoot={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":32,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":90,"key_label":0,"unicode":122,"location":0,"echo":false,"script":null)]
}}"""

    return f"""; Engine configuration file.
; Generated by AI Game Dev IDE.
;
; Format:
;   [section] ; section goes between []
;   param=value ; assign values to parameters

config_version=5

[application]

config/name="{game_name}"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.2", "Forward Plus")
config/icon="res://icon.svg"

[display]

window/size/viewport_width=1280
window/size/viewport_height=720
window/stretch/mode="canvas_items"

[input]

move_right={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":68,"key_label":0,"unicode":100,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194321,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}
move_left={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":97,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194319,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}
jump={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":32,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":87,"key_label":0,"unicode":119,"location":0,"echo":false,"script":null)]
}}{extra_inputs}

[layer_names]

2d_physics/layer_1="Player"
2d_physics/layer_2="Enemies"
2d_physics/layer_3="World"
2d_physics/layer_4="Collectibles"

[rendering]

textures/canvas_textures/default_texture_filter=0
"""


def _safe_filename(name: str) -> str:
    """Convert entity name to a safe lowercase filename slug."""
    import re
    slug = name.lower().replace(" ", "_").replace("-", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "entity"


def _safe_node_name(name: str) -> str:
    """Convert entity name to a valid Godot node name (PascalCase, no special chars)."""
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", name)
    return cleaned.replace(" ", "") or "Entity"


def _generate_main_scene(entities: list[dict[str, Any]], game_type: str = "arcade") -> str:
    """Return a minimal main.tscn that provides a ground and instances entities."""
    uid = uuid4().hex[:8]
    shape_id = f"RectangleShape2D_{uid}"
    load_steps = 1 + len(entities)

    ext_res_lines = []
    for i, entity in enumerate(entities):
        fname = _safe_filename(entity.get("name", f"Entity{i}"))
        ext_res_lines.append(
            f'[ext_resource type="PackedScene" path="res://scenes/{fname}.tscn" id="{i + 1}"]'
        )

    # Position entities based on their type for better layout
    instance_lines = []
    for i, entity in enumerate(entities):
        node_name = _safe_node_name(entity.get("name", f"Entity{i}"))
        etype = entity.get("type", "character").lower()

        # Smart positioning based on entity type and game type
        if etype in ("ui", "display"):
            x_pos, y_pos = 640, 40  # Top center for UI
        elif etype in ("environment", "background"):
            x_pos, y_pos = 640, 360  # Center for backgrounds
        elif etype in ("character", "player", "vehicle"):
            if game_type == "flappy":
                x_pos, y_pos = 120, 300  # Left side for flappy bird
            elif game_type == "racing":
                x_pos, y_pos = 640, 500  # Bottom center for racing
            else:
                x_pos, y_pos = 200, 500  # Left area for player
        elif etype in ("enemy", "boss"):
            x_pos, y_pos = 800 + i * 100, 500  # Right side for enemies
        elif etype in ("obstacle",):
            x_pos, y_pos = 400 + i * 150, 400  # Mid area for obstacles
        elif etype in ("collectible", "trigger"):
            x_pos, y_pos = 300 + i * 120, 350  # Scattered for collectibles
        elif etype in ("projectile",):
            x_pos, y_pos = 0, -100  # Off-screen for projectile templates
        else:
            x_pos, y_pos = 100 + i * 200, 500

        instance_lines.append(
            f'[node name="{node_name}" parent="." instance=ExtResource("{i + 1}")]\n'
            f"position = Vector2({x_pos}, {y_pos})"
        )

    ext_res_block = "\n".join(ext_res_lines)
    instance_block = "\n\n".join(instance_lines)

    return f"""[gd_scene load_steps={load_steps} format=3 uid="uid://{uid}"]

{ext_res_block}

[sub_resource type="RectangleShape2D" id="{shape_id}"]
size = Vector2(1280, 32)

[node name="Main" type="Node2D"]

[node name="Ground" type="StaticBody2D" parent="."]
position = Vector2(640, 700)

[node name="CollisionShape2D" type="CollisionShape2D" parent="Ground"]
shape = SubResource("{shape_id}")

{instance_block}
"""


def _generate_icon_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">
  <rect width="64" height="64" rx="8" fill="#4A90E2"/>
  <text x="32" y="44" font-size="32" text-anchor="middle" fill="#fff">G</text>
</svg>
"""


def _generate_readme(game_type: str, mechanics: list[str]) -> str:
    mech_str = ", ".join(mechanics) if mechanics else "standard"
    return f"""
Auto-generated Godot 4.x project by AI Game Dev IDE.

## Details
- **Type:** {game_type}
- **Mechanics:** {mech_str}

## How to Run
1. Open this folder in Godot 4.2 or later
2. Press **F5** to play

## Controls
- **Arrow keys / WASD** — move
- **Space / W** — jump

## Structure
```
scenes/     — .tscn scene files
scripts/    — GDScript (.gd) files
assets/     — Sprites and textures
```

*Generated by AI Game Dev IDE*
"""


class AIOrchestrator:
    def _infer_game_type(self, prompt: str) -> str:
        lower = prompt.lower()
        if any(k in lower for k in ("platform", "platformer")):
            return "platformer"
        if any(k in lower for k in ("shoot", "shooter", "shmup", "bullet")):
            return "shooter"
        if any(k in lower for k in ("racing", "race", "driving", "drift", "kart")):
            return "racing"
        if any(k in lower for k in ("puzzle", "match", "tetris", "block")):
            return "puzzle"
        if any(k in lower for k in ("rpg", "role-playing", "dungeon", "adventure")):
            return "rpg"
        if any(k in lower for k in ("tower", "defense", "td", "defend")):
            return "tower_defense"
        if any(k in lower for k in ("flappy", "bird", "fly", "flying")):
            return "flappy"
        if any(k in lower for k in ("snake",)):
            return "snake"
        if any(k in lower for k in ("space", "asteroid", "invader")):
            return "space_shooter"
        if any(k in lower for k in ("fighting", "fighter", "brawl", "combat")):
            return "fighting"
        if any(k in lower for k in ("survivor", "roguelike", "survival")):
            return "survival"
        if any(k in lower for k in ("top-down", "topdown", "top down")):
            return "topdown"
        return "arcade"

    def _infer_entities(self, prompt: str) -> list[str]:
        lower = prompt.lower()
        game_type = self._infer_game_type(prompt)

        # Game-type-specific entity sets for richer generation
        type_entities: dict[str, list[str]] = {
            "platformer":    ["Player", "Enemy", "Coin", "Platform", "Goal"],
            "shooter":       ["Player Ship", "Enemy Ship", "Bullet", "Power Up", "Boss"],
            "racing":        ["Player Car", "AI Opponent Car", "Track", "Checkpoint", "Power-Up Item"],
            "puzzle":        ["Puzzle Piece", "Grid", "Score Display", "Timer"],
            "rpg":           ["Hero", "Enemy", "NPC", "Treasure Chest", "Health Potion"],
            "tower_defense": ["Tower", "Enemy Wave", "Path", "Base", "Projectile"],
            "flappy":        ["Bird", "Pipe", "Ground", "Background", "Score Text", "Game Over Screen"],
            "snake":         ["Snake Head", "Snake Body", "Food", "Wall", "Score Display"],
            "space_shooter": ["Player Ship", "Alien", "Asteroid", "Bullet", "Shield Power-Up"],
            "fighting":      ["Fighter 1", "Fighter 2", "Health Bar", "Arena"],
            "survival":      ["Player", "Enemy Horde", "Weapon", "Health Pack", "XP Orb"],
            "topdown":       ["Player", "Enemy", "Projectile", "Wall", "Pickup"],
            "arcade":        ["Player", "Enemy", "Coin", "Obstacle", "Power Up"],
        }

        entities = list(type_entities.get(game_type, type_entities["arcade"]))

        # Add extras from prompt
        if any(k in lower for k in ("boss", "knight")):
            entities.append("Boss")
        if any(k in lower for k in ("coin", "collect", "collectible")) and "Coin" not in entities:
            entities.append("Coin")
        if any(k in lower for k in ("enemy", "enemies", "monster")) and not any("enemy" in e.lower() for e in entities):
            entities.append("Enemy")

        return list(dict.fromkeys(entities))  # Deduplicate preserving order

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = [l for l in text.splitlines() if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}

    def _fallback_design(self, prompt: str) -> dict[str, Any]:
        game_type = self._infer_game_type(prompt)
        entities = self._infer_entities(prompt)

        # Game-type-specific mechanics instead of always platformer
        type_mechanics: dict[str, list[str]] = {
            "platformer":    ["jump", "gravity", "double_jump", "wall_slide", "collect_coins", "moving_platforms"],
            "shooter":       ["shoot", "dodge", "power_ups", "wave_enemies", "boss_fights", "bullet_patterns"],
            "racing":        ["acceleration", "steering", "drifting", "boost", "lap_tracking", "AI_opponents", "checkpoints"],
            "puzzle":        ["drag_drop", "match_3", "rotate", "clear_lines", "combo_scoring", "timer"],
            "rpg":           ["attack", "defend", "heal", "inventory", "level_up", "dialogue"],
            "tower_defense": ["place_towers", "upgrade", "enemy_waves", "resource_management", "path_finding"],
            "flappy":        ["tap_to_fly", "gravity", "pipe_obstacles", "score_counting", "increasing_speed"],
            "snake":         ["grid_movement", "grow_on_eat", "self_collision", "wall_collision", "increasing_speed"],
            "space_shooter": ["shoot", "dodge", "shield", "power_ups", "asteroid_field", "boss_fights"],
            "fighting":      ["punch", "kick", "block", "special_move", "health_bars", "combos"],
            "survival":      ["auto_attack", "enemy_waves", "level_up", "weapon_choice", "increasing_difficulty"],
            "topdown":       ["8_directional_movement", "shoot", "dodge", "pickups", "enemy_AI"],
            "arcade":        ["jump", "gravity", "collect", "avoid_enemies", "power_ups", "increasing_difficulty"],
        }
        type_win: dict[str, list[str]] = {
            "platformer":    ["Reach the end of the level", "Collect all coins"],
            "shooter":       ["Defeat all waves", "Defeat the boss"],
            "racing":        ["Complete all laps first", "Beat the opponents"],
            "puzzle":        ["Clear all blocks", "Reach the target score"],
            "rpg":           ["Defeat the final boss", "Complete all quests"],
            "tower_defense": ["Survive all waves", "Protect the base"],
            "flappy":        ["Survive as long as possible", "Beat high score"],
            "snake":         ["Grow to maximum length", "Beat high score"],
            "space_shooter": ["Destroy all aliens", "Survive the asteroid field"],
            "fighting":      ["Deplete opponent health", "Win 3 rounds"],
            "survival":      ["Survive as long as possible", "Reach max level"],
            "topdown":       ["Clear all enemies", "Reach the exit"],
            "arcade":        ["Reach target score", "Survive until level complete"],
        }

        mechanics = type_mechanics.get(game_type, type_mechanics["arcade"])
        win_conditions = type_win.get(game_type, type_win["arcade"])

        return {
            "summary": f"Generated {game_type} game with {len(entities)} entities and {len(mechanics)} core mechanics.",
            "game_type": game_type,
            "mechanics": mechanics,
            "entities": entities,
            "win_conditions": win_conditions,
            "technical_requirements": {"framework": "canvas", "width": 800, "height": 600},
        }

    def _fallback_code(self, prompt: str) -> dict[str, Any]:
        game_type = self._infer_game_type(prompt)
        html = self._self_contained_html_game(game_type)
        return {
            "summary": "Generated starter HTML game using deterministic fallback.",
            "files": {"index.html": html},
            "entry_point": "index.html",
            "dependencies": [],
        }

    def _self_contained_html_game(self, game_type: str) -> str:
        if game_type == "racing":
            return self._fallback_racing_game()
        if game_type in ("flappy", "flappy_bird"):
            return self._fallback_flappy_game()
        if game_type == "snake":
            return self._fallback_snake_game()
        if game_type in ("shooter", "space_shooter"):
            return self._fallback_shooter_game()
        return self._fallback_platformer_game()

    def _fallback_platformer_game(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Platformer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W,H;function resize(){W=C.width=innerWidth;H=C.height=innerHeight}
resize();addEventListener('resize',resize);
const K={};addEventListener('keydown',e=>K[e.code]=true);addEventListener('keyup',e=>K[e.code]=false);
const G=0.6,JUMP=-13,SPD=5;
let state='menu',score=0,lives=3,level=1,camX=0,particles=[];
let P={x:100,y:0,w:28,h:36,vx:0,vy:0,grounded:false,facing:1,frame:0,ft:0};
function mkPlatforms(lvl){
  let p=[{x:0,y:H-40,w:W*3,h:40,clr:'#2d5a27'}];
  for(let i=0;i<12+lvl*3;i++){
    p.push({x:150+i*180+Math.random()*80,y:H-120-Math.random()*280,w:80+Math.random()*60,h:16,clr:'#'+['5a3a1a','4a6741','3a4a6a'][i%3]});
  }return p;
}
function mkCoins(plats){
  let c=[];plats.forEach((p,i)=>{if(i>0&&Math.random()>0.3)c.push({x:p.x+p.w/2,y:p.y-25,r:8,alive:true,t:Math.random()*6.28});});return c;
}
function mkEnemies(plats){
  let e=[];plats.forEach((p,i)=>{if(i>2&&Math.random()>0.5)e.push({x:p.x+10,y:p.y-24,w:24,h:24,vx:1.5,platform:p,alive:true});});return e;
}
let platforms,coins,enemies;
function initLevel(){platforms=mkPlatforms(level);coins=mkCoins(platforms);enemies=mkEnemies(platforms);P.x=100;P.y=H-120;P.vy=0;P.vx=0;camX=0;}
initLevel();
function burst(x,y,clr,n=10){for(let i=0;i<n;i++)particles.push({x,y,vx:(Math.random()-0.5)*4,vy:-Math.random()*5,life:1,clr,r:Math.random()*3+1});}
function update(dt){
  if(state!=='play')return;
  if(K['ArrowLeft']||K['KeyA']){P.vx=-SPD;P.facing=-1}
  else if(K['ArrowRight']||K['KeyD']){P.vx=SPD;P.facing=1}
  else P.vx*=0.8;
  if((K['Space']||K['ArrowUp']||K['KeyW'])&&P.grounded){P.vy=JUMP;P.grounded=false}
  P.vy+=G;P.x+=P.vx;P.y+=P.vy;P.grounded=false;
  platforms.forEach(p=>{if(P.x+P.w>p.x&&P.x<p.x+p.w&&P.y+P.h>=p.y&&P.y+P.h<=p.y+16&&P.vy>=0){P.y=p.y-P.h;P.vy=0;P.grounded=true}});
  if(P.y>H+100){lives--;burst(P.x,H,`#f00`,20);if(lives<=0)state='over';else{P.x=100;P.y=H-120;P.vy=0}}
  coins.forEach(c=>{if(!c.alive)return;c.t+=dt*3;let dx=P.x+P.w/2-c.x,dy=P.y+P.h/2-c.y;if(Math.sqrt(dx*dx+dy*dy)<20){c.alive=false;score+=10;burst(c.x,c.y,'#ffd700',12)}});
  enemies.forEach(e=>{if(!e.alive)return;e.x+=e.vx;if(e.x<e.platform.x||e.x+e.w>e.platform.x+e.platform.w)e.vx*=-1;
    let dx=P.x-e.x,dy=P.y-e.y;if(Math.abs(dx)<P.w&&Math.abs(dy)<P.h){if(P.vy>0&&P.y<e.y){e.alive=false;P.vy=-8;score+=25;burst(e.x,e.y,'#e74c3c',15)}
    else{lives--;burst(P.x,P.y,'#f00',10);P.x=100;P.y=H-120;P.vy=0;if(lives<=0)state='over'}}});
  if(coins.every(c=>!c.alive)){level++;initLevel()}
  camX+=(P.x-W/3-camX)*0.1;
  particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=0.15;p.life-=0.025});
  particles=particles.filter(p=>p.life>0);
  P.ft+=dt;if(P.ft>0.12){P.frame=(P.frame+1)%4;P.ft=0}
}
function drawBg(){
  let grd=X.createLinearGradient(0,0,0,H);grd.addColorStop(0,'#0b0e17');grd.addColorStop(0.5,'#1a1a2e');grd.addColorStop(1,'#16213e');
  X.fillStyle=grd;X.fillRect(0,0,W,H);
  for(let i=0;i<50;i++){X.fillStyle=`rgba(255,255,255,${0.3+Math.random()*0.5})`;X.fillRect((i*97+camX*0.05)%W,i*14%H,1.5,1.5)}
}
function drawPlayer(){
  let sx=P.x-camX,sy=P.y;X.save();X.translate(sx+P.w/2,sy+P.h/2);X.scale(P.facing,1);
  X.fillStyle='#4a90e2';X.fillRect(-P.w/2,-P.h/2,P.w,P.h);
  X.fillStyle='#3a7bd5';X.fillRect(-P.w/2,P.h/4,P.w,P.h/4);
  X.fillStyle='#fff';X.fillRect(P.facing>0?2:-10,-P.h/2+6,5,5);
  X.fillStyle='#000';X.fillRect(P.facing>0?4:-8,-P.h/2+7,2,3);
  if(!P.grounded){X.fillStyle='#4a90e2';X.fillRect(-P.w/2-3,-2,3,8);X.fillRect(P.w/2,2,3,8)}
  X.restore();
}
function draw(){
  drawBg();
  platforms.forEach(p=>{let px=p.x-camX;X.fillStyle=p.clr;X.fillRect(px,p.y,p.w,p.h);
    X.fillStyle='rgba(255,255,255,0.1)';X.fillRect(px,p.y,p.w,2)});
  coins.forEach(c=>{if(!c.alive)return;let cx=c.x-camX;X.save();X.translate(cx,c.y);
    X.fillStyle='#ffd700';X.shadowColor='#ffd700';X.shadowBlur=10;
    X.beginPath();X.ellipse(0,0,c.r*Math.abs(Math.cos(c.t)),c.r,0,0,Math.PI*2);X.fill();
    X.shadowBlur=0;X.fillStyle='#fff8dc';X.beginPath();X.ellipse(-2,-2,2,2,0,0,Math.PI*2);X.fill();X.restore()});
  enemies.forEach(e=>{if(!e.alive)return;let ex=e.x-camX;X.fillStyle='#e74c3c';
    X.beginPath();X.ellipse(ex+e.w/2,e.y+e.h/2,e.w/2,e.h/2,0,0,Math.PI*2);X.fill();
    X.fillStyle='#fff';X.fillRect(ex+4,e.y+6,5,5);X.fillRect(ex+e.w-9,e.y+6,5,5);
    X.fillStyle='#000';X.fillRect(ex+5,e.y+8,3,3);X.fillRect(ex+e.w-8,e.y+8,3,3)});
  drawPlayer();
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x-camX,p.y,p.r,0,6.28);X.fill()});
  X.globalAlpha=1;
  X.fillStyle='#fff';X.font='bold 18px system-ui';X.fillText(`Score: ${score}`,16,30);X.fillText(`Lives: ${lives}`,16,54);X.fillText(`Level: ${level}`,16,78);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#4a90e2';X.fillText('PLATFORMER',W/2,H/2-60);
    X.font='20px system-ui';X.fillStyle='#aaa';X.fillText('Arrow Keys / WASD to move, Space to jump',W/2,H/2);
    X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50);X.textAlign='left'}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-40);
    X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score}`,W/2,H/2+10);
    X.fillText('Press SPACE to Restart',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if(state==='menu'&&K['Space']){state='play';K['Space']=false}
  if(state==='over'&&K['Space']){state='play';score=0;lives=3;level=1;initLevel();K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

    def _fallback_racing_game(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Racing</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W,H;function resize(){W=C.width=960;H=C.height=640;C.style.maxWidth='100vw';C.style.maxHeight='100vh'}
resize();
const K={};addEventListener('keydown',e=>K[e.code]=true);addEventListener('keyup',e=>K[e.code]=false);
let state='menu',lap=0,totalLaps=3,score=0,raceTime=0,driftScore=0;
const trackPts=[{x:480,y:560},{x:160,y:520},{x:80,y:380},{x:100,y:200},{x:200,y:80},{x:400,y:40},
{x:600,y:60},{x:780,y:160},{x:860,y:340},{x:820,y:480},{x:700,y:560},{x:480,y:560}];
function getTrackPoint(t){
  let i=Math.floor(t)%trackPts.length,n=(i+1)%trackPts.length,f=t-Math.floor(t);
  return{x:trackPts[i].x+(trackPts[n].x-trackPts[i].x)*f,y:trackPts[i].y+(trackPts[n].y-trackPts[i].y)*f};
}
let P={x:480,y:540,angle:-Math.PI/2,speed:0,maxSpeed:5,drift:false,driftAngle:0,tireMarks:[]};
let AI={x:480,y:560,angle:-Math.PI/2,speed:2.5,t:0.5};
let checkpointsPassed=0,checkpoints=[0.25,0.5,0.75],cpFlags=[false,false,false];
let particles=[],boosts=[{x:400,y:300,active:true},{x:700,y:200,active:true}];
function drawCar(x,y,angle,clr,isPlayer){
  X.save();X.translate(x,y);X.rotate(angle);
  // Body
  X.fillStyle=clr;X.beginPath();X.moveTo(-10,-18);X.lineTo(10,-18);X.lineTo(12,-6);X.lineTo(12,14);
  X.lineTo(8,18);X.lineTo(-8,18);X.lineTo(-12,14);X.lineTo(-12,-6);X.closePath();X.fill();
  // Windshield
  let grd=X.createLinearGradient(0,-14,0,-4);grd.addColorStop(0,'rgba(150,200,255,0.8)');grd.addColorStop(1,'rgba(100,150,200,0.3)');
  X.fillStyle=grd;X.fillRect(-7,-14,14,8);
  // Wheels
  X.fillStyle='#222';X.fillRect(-14,-14,4,8);X.fillRect(10,-14,4,8);X.fillRect(-14,8,4,8);X.fillRect(10,8,4,8);
  // Headlights
  if(isPlayer){X.fillStyle='#ffe066';X.fillRect(-8,-19,4,2);X.fillRect(4,-19,4,2)}
  // Spoiler
  X.fillStyle='#333';X.fillRect(-9,16,18,3);
  X.restore();
  // Exhaust particles
  if(isPlayer&&P.speed>2){
    for(let i=0;i<2;i++)particles.push({x:x-Math.cos(angle)*20+(Math.random()-0.5)*6,
      y:y-Math.sin(angle)*20+(Math.random()-0.5)*6,vx:(Math.random()-0.5)*2,vy:(Math.random()-0.5)*2,
      life:0.5,clr:'rgba(200,200,200,',r:Math.random()*3+1});
  }
}
function drawTrack(){
  // Grass
  X.fillStyle='#1a4a1a';X.fillRect(0,0,W,H);
  // Track
  X.strokeStyle='#555';X.lineWidth=80;X.lineCap='round';X.lineJoin='round';
  X.beginPath();X.moveTo(trackPts[0].x,trackPts[0].y);
  for(let i=1;i<trackPts.length;i++)X.lineTo(trackPts[i].x,trackPts[i].y);
  X.stroke();
  // Road surface
  X.strokeStyle='#444';X.lineWidth=76;X.beginPath();X.moveTo(trackPts[0].x,trackPts[0].y);
  for(let i=1;i<trackPts.length;i++)X.lineTo(trackPts[i].x,trackPts[i].y);X.stroke();
  // Center dashes
  X.strokeStyle='#666';X.lineWidth=2;X.setLineDash([20,15]);
  X.beginPath();X.moveTo(trackPts[0].x,trackPts[0].y);
  for(let i=1;i<trackPts.length;i++)X.lineTo(trackPts[i].x,trackPts[i].y);X.stroke();
  X.setLineDash([]);
  // Start/Finish line
  X.fillStyle='#fff';for(let i=0;i<8;i++)for(let j=0;j<4;j++){
    if((i+j)%2===0){X.fillRect(450+i*8,545+j*5,8,5)}}
  // Boosts
  boosts.forEach(b=>{if(!b.active)return;X.save();X.translate(b.x,b.y);
    X.fillStyle='rgba(0,200,255,0.3)';X.shadowColor='#0af';X.shadowBlur=15;
    X.fillRect(-12,-12,24,24);X.shadowBlur=0;X.fillStyle='#0af';X.font='bold 14px system-ui';
    X.textAlign='center';X.fillText('>>',0,5);X.restore()});
}
function drawTireMarks(){P.tireMarks.forEach((m,i)=>{X.fillStyle=`rgba(40,40,40,${m.a})`;X.fillRect(m.x-1,m.y-1,3,3)})}
function distToTrack(px,py){
  let minD=Infinity;
  for(let i=0;i<trackPts.length-1;i++){
    let ax=trackPts[i].x,ay=trackPts[i].y,bx=trackPts[i+1].x,by=trackPts[i+1].y;
    let t=Math.max(0,Math.min(1,((px-ax)*(bx-ax)+(py-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2)));
    let dx=px-(ax+t*(bx-ax)),dy=py-(ay+t*(by-ay));minD=Math.min(minD,Math.sqrt(dx*dx+dy*dy));
  }return minD;
}
function update(dt){
  if(state!=='play')return;raceTime+=dt;
  let acc=K['ArrowUp']||K['KeyW']?0.12:0,brk=K['ArrowDown']||K['KeyS']?0.15:0;
  P.speed=Math.max(0,Math.min(P.maxSpeed,P.speed+acc-brk-0.02));
  let turnRate=0.04*(P.speed/P.maxSpeed);
  if(K['ArrowLeft']||K['KeyA'])P.angle-=turnRate;
  if(K['ArrowRight']||K['KeyD'])P.angle+=turnRate;
  if(K['Space']&&P.speed>2){P.drift=true;P.tireMarks.push({x:P.x,y:P.y,a:0.5});
    if(P.tireMarks.length>500)P.tireMarks.shift();driftScore+=dt*100;
    P.speed*=0.995;P.angle+=(K['ArrowLeft']||K['KeyA']?-0.02:K['ArrowRight']||K['KeyD']?0.02:0);
  }else P.drift=false;
  P.x+=Math.cos(P.angle)*P.speed*60*dt;P.y+=Math.sin(P.angle)*P.speed*60*dt;
  // Off-track slowdown
  if(distToTrack(P.x,P.y)>42)P.speed*=0.95;
  // Keep on screen
  P.x=Math.max(10,Math.min(W-10,P.x));P.y=Math.max(10,Math.min(H-10,P.y));
  // Boosts
  boosts.forEach(b=>{if(!b.active)return;if(Math.abs(P.x-b.x)<16&&Math.abs(P.y-b.y)<16){
    P.speed=Math.min(P.maxSpeed*1.5,P.speed+3);b.active=false;setTimeout(()=>b.active=true,5000);
    for(let i=0;i<15;i++)particles.push({x:b.x,y:b.y,vx:(Math.random()-0.5)*6,vy:(Math.random()-0.5)*6,life:0.8,clr:'rgba(0,170,255,',r:2})}});
  // Checkpoints
  for(let i=0;i<checkpoints.length;i++){let cp=getTrackPoint(checkpoints[i]*trackPts.length);
    if(!cpFlags[i]&&Math.abs(P.x-cp.x)<30&&Math.abs(P.y-cp.y)<30){cpFlags[i]=true;checkpointsPassed++}}
  // Lap detection
  if(checkpointsPassed>=3&&Math.abs(P.x-480)<30&&Math.abs(P.y-550)<30){
    lap++;cpFlags=[false,false,false];checkpointsPassed=0;score+=1000;
    if(lap>=totalLaps)state='win'}
  // AI
  AI.t+=AI.speed*dt*0.15;if(AI.t>=trackPts.length)AI.t-=trackPts.length;
  let target=getTrackPoint(AI.t);AI.angle=Math.atan2(target.y-AI.y,target.x-AI.x);
  AI.x+=(target.x-AI.x)*dt*2;AI.y+=(target.y-AI.y)*dt*2;
  // Particles update
  particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.life-=dt*2});particles=particles.filter(p=>p.life>0);
}
function drawHUD(){
  X.fillStyle='rgba(0,0,0,0.5)';X.fillRect(10,10,200,90);
  X.fillStyle='#fff';X.font='bold 16px system-ui';
  X.fillText(`Speed: ${Math.round(P.speed*20)} km/h`,20,32);
  X.fillText(`Lap: ${Math.min(lap+1,totalLaps)} / ${totalLaps}`,20,54);
  X.fillText(`Drift: ${Math.round(driftScore)}`,20,76);
  X.fillText(`Time: ${raceTime.toFixed(1)}s`,20,96);
  // Speed bar
  X.fillStyle='#333';X.fillRect(W-160,16,140,12);
  X.fillStyle=P.speed>P.maxSpeed?'#0af':'#4a90e2';X.fillRect(W-160,16,140*(P.speed/P.maxSpeed),12);
}
function draw(){
  X.clearRect(0,0,W,H);drawTrack();drawTireMarks();
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr+p.life+')';X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill()});
  X.globalAlpha=1;
  drawCar(AI.x,AI.y,AI.angle,'#27ae60',false);drawCar(P.x,P.y,P.angle,'#e74c3c',true);drawHUD();
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 52px system-ui';X.fillStyle='#e74c3c';X.shadowColor='#e74c3c';X.shadowBlur=20;
    X.fillText('DRIFT RACER',W/2,H/2-80);X.shadowBlur=0;
    X.font='20px system-ui';X.fillStyle='#ccc';
    X.fillText('Arrow Keys / WASD to drive | SPACE to drift',W/2,H/2-10);
    X.fillText('Complete 3 laps to win!',W/2,H/2+25);
    X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+80);X.textAlign='left'}
  if(state==='win'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#ffd700';X.shadowColor='#ffd700';X.shadowBlur=15;
    X.fillText('YOU WIN!',W/2,H/2-40);X.shadowBlur=0;
    X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Time: ${raceTime.toFixed(1)}s | Drift Score: ${Math.round(driftScore)}`,W/2,H/2+10);
    X.fillText('Press SPACE to Race Again',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if((state==='menu'||state==='win')&&K['Space']){state='play';lap=0;raceTime=0;driftScore=0;score=0;
    P.x=480;P.y=540;P.angle=-Math.PI/2;P.speed=0;P.tireMarks=[];AI.t=0.5;K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

    def _fallback_flappy_game(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Flappy</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W=480,H=640;C.width=W;C.height=H;
const K={};addEventListener('keydown',e=>{K[e.code]=true;if(e.code==='Space')e.preventDefault()});
addEventListener('keyup',e=>K[e.code]=false);
C.addEventListener('click',()=>flap());
let state='menu',score=0,best=0,gx=0;
let bird={x:120,y:H/2,vy:0,angle:0,wing:0};
let pipes=[],particles=[];
function resetGame(){bird.y=H/2;bird.vy=0;pipes=[];score=0;gx=0;mkPipe()}
function mkPipe(){let gap=150,gy=100+Math.random()*(H-250);pipes.push({x:W+20,gapY:gy,gapH:gap,passed:false})}
function flap(){if(state==='menu'){state='play';resetGame()}else if(state==='over'){state='play';resetGame()}
  if(state==='play'){bird.vy=-7.5;bird.wing=1}}
function update(dt){
  if(state!=='play')return;
  bird.vy+=0.35;bird.y+=bird.vy;bird.wing=Math.max(0,bird.wing-dt*8);
  bird.angle=Math.max(-0.5,Math.min(1.2,bird.vy*0.08));
  gx-=3;
  pipes.forEach(p=>{p.x-=3});
  if(pipes.length===0||pipes[pipes.length-1].x<W-200)mkPipe();
  pipes=pipes.filter(p=>p.x>-60);
  pipes.forEach(p=>{
    if(!p.passed&&p.x+40<bird.x){p.passed=true;score++;best=Math.max(best,score)}
    if(bird.x+14>p.x&&bird.x-14<p.x+50){if(bird.y-12<p.gapY||bird.y+12>p.gapY+p.gapH){die()}}
  });
  if(bird.y>H-50||bird.y<0)die();
}
function die(){state='over';for(let i=0;i<20;i++)particles.push({x:bird.x,y:bird.y,vx:(Math.random()-0.5)*8,vy:(Math.random()-0.5)*8,life:1,clr:'#f1c40f',r:Math.random()*3+1})}
function drawBird(x,y,angle){
  X.save();X.translate(x,y);X.rotate(angle);
  // Body
  X.fillStyle='#f1c40f';X.beginPath();X.ellipse(0,0,16,13,0,0,Math.PI*2);X.fill();
  // Wing
  let wy=bird.wing*-6;X.fillStyle='#e67e22';X.beginPath();X.ellipse(-4,wy+2,10,6,bird.wing*-0.3,0,Math.PI*2);X.fill();
  // Eye
  X.fillStyle='#fff';X.beginPath();X.arc(8,-3,5,0,Math.PI*2);X.fill();
  X.fillStyle='#000';X.beginPath();X.arc(9,-3,2.5,0,Math.PI*2);X.fill();
  // Beak
  X.fillStyle='#e74c3c';X.beginPath();X.moveTo(14,-2);X.lineTo(22,1);X.lineTo(14,4);X.closePath();X.fill();
  X.restore();
}
function drawPipe(p){
  let grd=X.createLinearGradient(p.x,0,p.x+50,0);grd.addColorStop(0,'#27ae60');grd.addColorStop(0.5,'#2ecc71');grd.addColorStop(1,'#27ae60');
  // Top pipe
  X.fillStyle=grd;X.fillRect(p.x,0,50,p.gapY);
  X.fillStyle='#219653';X.fillRect(p.x-4,p.gapY-20,58,20);
  // Bottom pipe
  X.fillStyle=grd;X.fillRect(p.x,p.gapY+p.gapH,50,H-p.gapY-p.gapH);
  X.fillStyle='#219653';X.fillRect(p.x-4,p.gapY+p.gapH,58,20);
}
function draw(){
  // Sky gradient
  let sky=X.createLinearGradient(0,0,0,H);sky.addColorStop(0,'#1a1a2e');sky.addColorStop(0.6,'#16213e');sky.addColorStop(1,'#0f3460');
  X.fillStyle=sky;X.fillRect(0,0,W,H);
  // Clouds
  X.fillStyle='rgba(255,255,255,0.05)';
  for(let i=0;i<5;i++){let cx=((i*120+gx*0.3)%600)-40;X.beginPath();X.arc(cx,60+i*40,30,0,Math.PI*2);X.arc(cx+25,55+i*40,22,0,Math.PI*2);X.fill()}
  pipes.forEach(drawPipe);
  // Ground
  X.fillStyle='#2d5a27';X.fillRect(0,H-50,W,50);
  X.fillStyle='#3a7d32';for(let i=0;i<W/20+2;i++){X.fillRect(((i*20+gx)%W+W)%W-10,H-50,20,4)}
  drawBird(bird.x,bird.y,bird.angle);
  // Particles
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill();
    p.x+=p.vx;p.y+=p.vy;p.vy+=0.2;p.life-=0.03});
  particles=particles.filter(p=>p.life>0);X.globalAlpha=1;
  // Score
  X.textAlign='center';X.font='bold 48px system-ui';X.fillStyle='#fff';X.strokeStyle='#000';X.lineWidth=3;
  X.strokeText(score,W/2,80);X.fillText(score,W/2,80);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.5)';X.fillRect(0,0,W,H);
    X.font='bold 42px system-ui';X.fillStyle='#f1c40f';X.fillText('FLAPPY BIRD',W/2,H/2-60);
    X.font='18px system-ui';X.fillStyle='#ccc';X.fillText('Press SPACE or Click to Flap',W/2,H/2);
    X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50)}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.6)';X.fillRect(0,0,W,H);
    X.font='bold 42px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-50);
    X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score}  Best: ${best}`,W/2,H/2+5);
    X.fillText('Press SPACE to Retry',W/2,H/2+50)}
  X.textAlign='left';
}
addEventListener('keydown',e=>{if(e.code==='Space')flap()});
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

    def _fallback_shooter_game(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Space Shooter</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#000;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W=640,H=800;C.width=W;C.height=H;
const K={};addEventListener('keydown',e=>K[e.code]=true);addEventListener('keyup',e=>K[e.code]=false);
let state='menu',score=0,lives=3,wave=1,spawnTimer=0;
let P={x:W/2,y:H-80,w:32,h:32,speed:5,shootTimer:0,shootRate:0.15};
let bullets=[],enemies=[],particles=[],stars=[];
for(let i=0;i<100;i++)stars.push({x:Math.random()*W,y:Math.random()*H,s:Math.random()*2+0.5,b:Math.random()});
function spawnEnemy(){
  let t=Math.random();
  if(t<0.6)enemies.push({x:Math.random()*(W-30)+15,y:-30,w:24,h:24,vy:2+wave*0.3,hp:1,type:'small',angle:0});
  else if(t<0.9)enemies.push({x:Math.random()*(W-40)+20,y:-40,w:36,h:36,vy:1.5+wave*0.2,hp:3,type:'medium',vx:Math.sin(Date.now()*0.001)*2,angle:0});
  else enemies.push({x:Math.random()*(W-50)+25,y:-50,w:48,h:48,vy:1+wave*0.15,hp:8,type:'boss',vx:0,angle:0});
}
function burst(x,y,clr,n=12){for(let i=0;i<n;i++)particles.push({x,y,vx:(Math.random()-0.5)*6,vy:(Math.random()-0.5)*6,life:1,clr,r:Math.random()*3+1})}
function update(dt){
  if(state!=='play')return;
  if(K['ArrowLeft']||K['KeyA'])P.x-=P.speed;if(K['ArrowRight']||K['KeyD'])P.x+=P.speed;
  if(K['ArrowUp']||K['KeyW'])P.y-=P.speed;if(K['ArrowDown']||K['KeyS'])P.y+=P.speed;
  P.x=Math.max(16,Math.min(W-16,P.x));P.y=Math.max(16,Math.min(H-16,P.y));
  P.shootTimer-=dt;if((K['Space']||K['KeyZ'])&&P.shootTimer<=0){
    bullets.push({x:P.x-6,y:P.y-20,vy:-10,w:3,h:12});bullets.push({x:P.x+6,y:P.y-20,vy:-10,w:3,h:12});
    P.shootTimer=P.shootRate}
  bullets.forEach(b=>{b.y+=b.vy});bullets=bullets.filter(b=>b.y>-20);
  spawnTimer-=dt;if(spawnTimer<=0){spawnEnemy();spawnTimer=Math.max(0.3,1.5-wave*0.1)}
  enemies.forEach(e=>{e.y+=e.vy;if(e.vx)e.x+=Math.sin(e.y*0.02)*e.vx;e.angle+=dt*2;
    if(e.y>H+50)e.hp=-1;
    bullets.forEach(b=>{if(b.vy<0&&Math.abs(b.x-e.x)<e.w/2+4&&Math.abs(b.y-e.y)<e.h/2+8){e.hp--;b.vy=99;
      burst(b.x,b.y,'#ffd700',5);if(e.hp<=0){score+=e.type==='boss'?100:e.type==='medium'?30:10;
        burst(e.x,e.y,e.type==='boss'?'#e74c3c':'#ff6b6b',e.type==='boss'?30:15)}}});
    if(e.hp>0&&Math.abs(P.x-e.x)<(P.w+e.w)/2&&Math.abs(P.y-e.y)<(P.h+e.h)/2){
      lives--;e.hp=0;burst(P.x,P.y,'#4a90e2',20);if(lives<=0)state='over'}
  });
  enemies=enemies.filter(e=>e.hp>0);
  if(enemies.length===0&&spawnTimer>0.5){wave++;spawnTimer=0.2}
  particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.life-=dt*2});particles=particles.filter(p=>p.life>0);
  stars.forEach(s=>{s.y+=s.s;if(s.y>H){s.y=0;s.x=Math.random()*W}s.b=0.3+Math.sin(Date.now()*0.003+s.x)*0.3});
}
function drawShip(x,y){
  X.save();X.translate(x,y);
  // Engine glow
  X.fillStyle='rgba(100,150,255,0.3)';X.shadowColor='#4a90e2';X.shadowBlur=15;
  X.beginPath();X.ellipse(0,18,8,12,0,0,Math.PI*2);X.fill();X.shadowBlur=0;
  // Body
  X.fillStyle='#4a90e2';X.beginPath();X.moveTo(0,-20);X.lineTo(-14,16);X.lineTo(0,10);X.lineTo(14,16);X.closePath();X.fill();
  // Cockpit
  X.fillStyle='#7ec8e3';X.beginPath();X.ellipse(0,-4,5,8,0,0,Math.PI*2);X.fill();
  // Wings
  X.fillStyle='#3a7bd5';X.beginPath();X.moveTo(-10,8);X.lineTo(-22,18);X.lineTo(-8,14);X.closePath();X.fill();
  X.beginPath();X.moveTo(10,8);X.lineTo(22,18);X.lineTo(8,14);X.closePath();X.fill();
  X.restore();
}
function drawEnemy(e){
  X.save();X.translate(e.x,e.y);
  if(e.type==='boss'){X.fillStyle='#e74c3c';X.beginPath();X.moveTo(0,-24);X.lineTo(-24,24);X.lineTo(24,24);X.closePath();X.fill();
    X.fillStyle='#c0392b';X.beginPath();X.arc(0,4,10,0,Math.PI*2);X.fill();
    X.fillStyle='#ff0';X.beginPath();X.arc(-6,-2,3,0,Math.PI*2);X.fill();X.beginPath();X.arc(6,-2,3,0,Math.PI*2);X.fill();
    // Health bar
    X.fillStyle='#333';X.fillRect(-20,-30,40,4);X.fillStyle='#e74c3c';X.fillRect(-20,-30,40*(e.hp/8),4);
  }else if(e.type==='medium'){X.fillStyle='#8e44ad';X.beginPath();X.arc(0,0,e.w/2,0,Math.PI*2);X.fill();
    X.fillStyle='#fff';X.beginPath();X.arc(-6,-4,3,0,Math.PI*2);X.fill();X.beginPath();X.arc(6,-4,3,0,Math.PI*2);X.fill();
  }else{X.fillStyle='#e67e22';X.rotate(e.angle);X.fillRect(-e.w/2,-e.h/2,e.w,e.h);
    X.fillStyle='#f39c12';X.fillRect(-e.w/4,-e.h/4,e.w/2,e.h/2)}
  X.restore();
}
function draw(){
  X.fillStyle='#050510';X.fillRect(0,0,W,H);
  stars.forEach(s=>{X.fillStyle=`rgba(255,255,255,${s.b})`;X.fillRect(s.x,s.y,s.s,s.s)});
  bullets.forEach(b=>{X.fillStyle='#7ec8e3';X.shadowColor='#4a90e2';X.shadowBlur=6;X.fillRect(b.x-1,b.y,b.w,b.h);X.shadowBlur=0});
  enemies.forEach(drawEnemy);
  if(state==='play')drawShip(P.x,P.y);
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill()});
  X.globalAlpha=1;
  X.fillStyle='#fff';X.font='bold 16px system-ui';X.fillText(`Score: ${score}`,16,28);X.fillText(`Lives: ${lives}`,16,50);X.fillText(`Wave: ${wave}`,16,72);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#4a90e2';X.shadowColor='#4a90e2';X.shadowBlur=20;
    X.fillText('SPACE SHOOTER',W/2,H/2-80);X.shadowBlur=0;
    X.font='18px system-ui';X.fillStyle='#aaa';X.fillText('WASD/Arrows to move | SPACE to shoot',W/2,H/2-10);
    X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50);X.textAlign='left'}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-40);
    X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score} | Wave: ${wave}`,W/2,H/2+10);
    X.fillText('Press SPACE to Retry',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if((state==='menu'||state==='over')&&K['Space']){state='play';score=0;lives=3;wave=1;spawnTimer=0;
    P.x=W/2;P.y=H-80;bullets=[];enemies=[];particles=[];K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

    def _fallback_snake_game(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Snake</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
const COLS=24,ROWS=18,SZ=32;let W=C.width=COLS*SZ,H=C.height=ROWS*SZ;
const K={};addEventListener('keydown',e=>{K[e.code]=true;if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault()});
addEventListener('keyup',e=>K[e.code]=false);
let state='menu',score=0,best=0,speed=8,moveTimer=0;
let snake,dir,food,particles=[];
function reset(){snake=[{x:12,y:9},{x:11,y:9},{x:10,y:9}];dir={x:1,y:0};speed=8;score=0;placeFood()}
function placeFood(){do{food={x:Math.floor(Math.random()*COLS),y:Math.floor(Math.random()*ROWS),pulse:0}}while(snake.some(s=>s.x===food.x&&s.y===food.y))}
reset();
function burst(x,y,clr,n=10){for(let i=0;i<n;i++)particles.push({x:x*SZ+SZ/2,y:y*SZ+SZ/2,vx:(Math.random()-0.5)*5,vy:(Math.random()-0.5)*5,life:1,clr,r:Math.random()*3+1})}
function update(dt){
  if(state!=='play')return;
  if((K['ArrowUp']||K['KeyW'])&&dir.y!==1){dir={x:0,y:-1}}
  if((K['ArrowDown']||K['KeyS'])&&dir.y!==-1){dir={x:0,y:1}}
  if((K['ArrowLeft']||K['KeyA'])&&dir.x!==1){dir={x:-1,y:0}}
  if((K['ArrowRight']||K['KeyD'])&&dir.x!==-1){dir={x:1,y:0}}
  moveTimer+=dt;if(moveTimer<1/speed)return;moveTimer=0;
  let head={x:snake[0].x+dir.x,y:snake[0].y+dir.y};
  if(head.x<0||head.x>=COLS||head.y<0||head.y>=ROWS||snake.some(s=>s.x===head.x&&s.y===head.y)){
    state='over';best=Math.max(best,score);burst(snake[0].x,snake[0].y,'#e74c3c',25);return}
  snake.unshift(head);
  if(head.x===food.x&&head.y===food.y){score+=10;burst(food.x,food.y,'#f1c40f',15);placeFood();
    if(score%50===0)speed=Math.min(20,speed+1)}
  else snake.pop();
  food.pulse+=dt*4;
}
function draw(){
  // Background grid
  X.fillStyle='#0d1117';X.fillRect(0,0,W,H);
  for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++){X.fillStyle=(r+c)%2===0?'#0d1117':'#111820';X.fillRect(c*SZ,r*SZ,SZ,SZ)}
  // Food
  let fx=food.x*SZ+SZ/2,fy=food.y*SZ+SZ/2,fr=SZ/2-4+Math.sin(food.pulse)*2;
  X.save();X.shadowColor='#e74c3c';X.shadowBlur=12;
  X.fillStyle='#e74c3c';X.beginPath();X.arc(fx,fy,fr,0,Math.PI*2);X.fill();
  X.shadowBlur=0;X.fillStyle='#ff6b6b';X.beginPath();X.arc(fx-3,fy-3,fr*0.4,0,Math.PI*2);X.fill();X.restore();
  // Snake
  snake.forEach((s,i)=>{
    let ratio=1-i/snake.length;let r=SZ/2-2-i*0.1;
    let hue=120+i*3;X.fillStyle=`hsl(${hue},70%,${40+ratio*20}%)`;
    X.beginPath();X.arc(s.x*SZ+SZ/2,s.y*SZ+SZ/2,Math.max(4,r),0,Math.PI*2);X.fill();
    if(i===0){// Eyes
      let ex1=s.x*SZ+SZ/2+dir.x*6-dir.y*5,ey1=s.y*SZ+SZ/2+dir.y*6+dir.x*5;
      let ex2=s.x*SZ+SZ/2+dir.x*6+dir.y*5,ey2=s.y*SZ+SZ/2+dir.y*6-dir.x*5;
      X.fillStyle='#fff';X.beginPath();X.arc(ex1,ey1,3.5,0,Math.PI*2);X.fill();
      X.beginPath();X.arc(ex2,ey2,3.5,0,Math.PI*2);X.fill();
      X.fillStyle='#000';X.beginPath();X.arc(ex1+dir.x,ey1+dir.y,1.5,0,Math.PI*2);X.fill();
      X.beginPath();X.arc(ex2+dir.x,ey2+dir.y,1.5,0,Math.PI*2);X.fill();
    }
  });
  // Particles
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill();
    p.x+=p.vx;p.y+=p.vy;p.life-=0.03});particles=particles.filter(p=>p.life>0);X.globalAlpha=1;
  // HUD
  X.fillStyle='#fff';X.font='bold 18px system-ui';X.fillText(`Score: ${score}`,12,28);
  X.fillText(`Best: ${best}`,W-120,28);X.fillText(`Speed: ${speed}`,W/2-40,28);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#2ecc71';X.shadowColor='#2ecc71';X.shadowBlur=15;
    X.fillText('SNAKE',W/2,H/2-60);X.shadowBlur=0;
    X.font='18px system-ui';X.fillStyle='#aaa';X.fillText('Arrow Keys / WASD to steer',W/2,H/2);
    X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50);X.textAlign='left'}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
    X.font='bold 48px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-40);
    X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score}  Best: ${best}`,W/2,H/2+10);
    X.fillText('Press SPACE to Retry',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if((state==='menu'||state==='over')&&K['Space']){state='play';reset();K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

    def _format_history(self, history: list[dict]) -> str:
        if not history:
            return ""
        lines = ["\nPREVIOUS CONVERSATION HISTORY:"]
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role.upper()}: {content}")
        lines.append("END HISTORY\n")
        return "\n".join(lines)

    async def generate_design(
        self,
        prompt: str,
        history: list[dict] | None = None,
    ) -> OrchestratorResult:
        system = (
            "You are an expert game design architect who creates DETAILED, SPECIFIC game designs. "
            "Analyze the request and return a COMPLETE Game Design Document as strict JSON.\n"
            "Do NOT include markdown formatting like ```json ... ``` or any text outside the JSON.\n\n"
            "IMPORTANT RULES:\n"
            "- Generate AT LEAST 5-8 entities for any game. Every game needs enemies, obstacles, "
            "collectibles, UI elements, and environmental objects — not just a player.\n"
            "- Mechanics MUST be specific to the game type (e.g., racing needs steering/drifting/boost, "
            "NOT jumping/gravity).\n"
            "- Entity names should be descriptive (e.g., 'Player Car', 'AI Opponent', 'Speed Boost', "
            "'Finish Line' for racing — NOT generic 'Player', 'Enemy').\n"
            "- Include visual/theme details in the summary.\n\n"
            "The JSON must strictly follow this schema:\n"
            "{\n"
            '  "summary": "Detailed overview including theme, art style, and gameplay feel",\n'
            '  "game_type": "One of: platformer, shooter, rpg, puzzle, arcade, racing, flappy, '
            'snake, space_shooter, fighting, survival, topdown, tower_defense",\n'
            '  "mechanics": ["List of 5-8 SPECIFIC core mechanics relevant to this game type"],\n'
            '  "entities": [\n'
            '    {"name": "Descriptive Name", "type": "character|enemy|collectible|obstacle|ui|environment", '
            '"behaviors": ["specific_behavior_1", "specific_behavior_2"]}\n'
            "  ],\n"
            '  "win_conditions": ["List of 2-3 win/lose conditions"],\n'
            '  "visual_style": {"theme": "e.g. neon, retro, pixel, minimalist", '
            '"primary_colors": ["#hex1", "#hex2", "#hex3"], '
            '"background": "#hex_bg_color"},\n'
            '  "technical_requirements": {"framework": "canvas", "width": 960, "height": 640}\n'
            "}"
        )
        history_text = self._format_history(history or [])
        full_prompt = f"{system}{history_text}\nCURRENT REQUEST: {prompt}"

        try:
            result = await provider_manager.generate(full_prompt, temperature=0.7)
            design = self._extract_json_object(result.text)
            if not design:
                design = self._fallback_design(prompt)
            summary = design.get("summary", "Generated game design.")
            return OrchestratorResult(summary=summary, payload=design, usage=result.usage)
        except Exception:
            design = self._fallback_design(prompt)
            return OrchestratorResult(
                summary=design["summary"],
                payload=design,
                usage=ProviderUsage(),
            )

    async def generate_code(
        self,
        prompt: str,
        design_doc: dict[str, Any] | None = None,
        history: list[dict] | None = None,
        realtime: Any = None,
        project_id: str | None = None,
    ) -> OrchestratorResult:
        """Full multi-agent pipeline: Design → Assets/Scripts/Scenes → HTML5 game + Godot files.

        All agents call Gemini via the shared ProviderManager. The final output
        includes a playable index.html for browser preview AND Godot 4.x project
        files (.gd scripts, .tscn scenes, project.godot) for engine export.
        """
        total_usage = ProviderUsage(provider="gemini", model="multi-agent-pipeline")
        errors: list[str] = []

        # ── Phase 1: Design Agent ── Generate game design doc via Gemini
        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "design", "status": "running", "message": "Designing game architecture..."})

        if not design_doc or not design_doc.get("entities"):
            try:
                design_result = await self.generate_design(prompt, history)
                design_doc = design_result.payload
                if design_result.usage.total_tokens:
                    total_usage.total_tokens = (total_usage.total_tokens or 0) + design_result.usage.total_tokens
            except Exception as e:
                errors.append(f"Design agent error: {e}")
                design_doc = self._fallback_design(prompt)

        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "design", "status": "complete",
                         "message": f"Game type: {design_doc.get('game_type', 'arcade')} with {len(design_doc.get('entities', []))} entities"})

        # Normalize entities
        entities_raw = design_doc.get("entities", ["Player"])
        entities = [_normalize_entity(e) for e in entities_raw]
        if not any(e["type"] in ("character", "player") for e in entities):
            entities.insert(0, _normalize_entity("Player"))

        # ── Phase 2: Parallel Agent Execution — Scripts, Scenes, Assets via Gemini
        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scripts", "status": "running",
                         "message": f"Generating GDScript for {len(entities)} entities..."})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scenes", "status": "running",
                         "message": f"Building Godot scenes..."})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assets", "status": "running",
                         "message": f"Creating sprite assets..."})

        script_tasks = [script_agent.run(e, design_doc) for e in entities]
        scene_tasks = [scene_agent.run(e, design_doc) for e in entities]
        asset_tasks = [asset_agent.run(e, design_doc) for e in entities]

        all_results = await asyncio.gather(
            *script_tasks, *scene_tasks, *asset_tasks,
            return_exceptions=True,
        )

        n = len(entities)
        script_map: dict[str, str] = {}
        scene_map: dict[str, str] = {}
        asset_map: dict[str, dict] = {}

        for i, entity in enumerate(entities):
            ename = _safe_filename(entity["name"])
            # Scripts
            res = all_results[i]
            if isinstance(res, Exception):
                errors.append(f"Script agent failed for {ename}: {res}")
                script_map[ename] = _fallback_script(entity)
            else:
                script_map[ename] = res
            # Scenes
            res = all_results[n + i]
            if isinstance(res, Exception):
                errors.append(f"Scene agent failed for {ename}: {res}")
                scene_map[ename] = f'[gd_scene format=3]\n[node name="{ename}" type="Node2D"]\n'
            else:
                scene_map[ename] = res
            # Assets
            res = all_results[2 * n + i]
            if isinstance(res, Exception):
                errors.append(f"Asset agent failed for {ename}: {res}")
                asset_map[ename] = {"spec": {}, "png_b64": None, "width": 32, "height": 32}
            else:
                asset_map[ename] = res

        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scripts", "status": "complete", "message": f"{len(script_map)} scripts generated"})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scenes", "status": "complete", "message": f"{len(scene_map)} scenes generated"})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assets", "status": "complete", "message": f"{len(asset_map)} assets generated"})

        # ── Phase 3: Generate comprehensive HTML5 game with full design context
        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assembler", "status": "running", "message": "Building playable HTML5 game..."})

        html_game = await self._generate_rich_html_game(prompt, design_doc, entities, script_map, asset_map, history)

        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assembler", "status": "complete", "message": "Game assembled successfully"})

        # ── Phase 4: Assemble ALL files — HTML5 preview + Godot project
        game_name = design_doc.get("game_type", "game").title() + " Game"
        files: dict[str, str] = {}

        # HTML5 playable game (browser preview)
        files["index.html"] = html_game

        # Godot project files
        files["project.godot"] = _generate_project_config(game_name, design_doc.get("game_type", "arcade"))
        files["scenes/main.tscn"] = _generate_main_scene(entities, design_doc.get("game_type", "arcade"))
        files["icon.svg"] = _generate_icon_svg()
        files["README.md"] = _generate_readme(
            design_doc.get("game_type", "arcade"),
            design_doc.get("mechanics", []),
        )

        for ename, content in script_map.items():
            if isinstance(content, str) and content.strip():
                files[f"scripts/{ename}.gd"] = content
        for ename, content in scene_map.items():
            if isinstance(content, str) and content.strip():
                files[f"scenes/{ename}.tscn"] = content

        summary = (
            f"Generated {design_doc.get('game_type', 'arcade')} game with "
            f"{len(entities)} entities, {len(script_map)} scripts, "
            f"{len(scene_map)} scenes. "
            f"Preview the HTML5 version in-browser or export the Godot 4.x project files."
        )
        if errors:
            summary += f" ({len(errors)} non-fatal warnings during generation)"

        payload = {
            "summary": summary,
            "files": files,
            "entry_point": "index.html",
            "dependencies": [],
            "design_doc": design_doc,
            "godot_stats": {
                "entities": len(entities),
                "scripts": len(script_map),
                "scenes": len(scene_map),
                "assets": len(asset_map),
            },
            "agent_errors": errors,
        }

        return OrchestratorResult(summary=summary, payload=payload, usage=total_usage)

    def _get_game_type_instructions(self, game_type: str, prompt: str) -> str:
        """Return detailed game-type-specific rendering and gameplay instructions."""
        instructions: dict[str, str] = {
            "racing": """RACING GAME SPECIFICS:
- TOP-DOWN VIEW with the track filling most of the canvas.
- Draw a PROPER RACE TRACK — curved roads with lane markings, grass/sand edges, grandstands.
  Use bezier curves or pre-defined path points. NOT a simple rectangle.
- Draw CARS that look like real top-down cars: body shape with rounded front, visible wheels,
  windshield, exhaust trail particles when accelerating.
- Implement REAL DRIFTING physics: when drift key is held, the car slides with reduced traction,
  leaving tire marks on the track. Award drift score.
- AI opponent cars that follow the track with some variation and can overtake.
- SPEEDOMETER as a visual gauge (arc with needle), not just a number.
- Lap counter, position indicator, minimap of the track.
- Checkpoints marked with visible flags or lines.
- Speed boost pads on the track with a glow effect.
- Camera follows the player car smoothly.
- Tire screech sound on drift, engine hum that changes pitch with speed.
- Finish line with checkered flag pattern.""",

            "platformer": """PLATFORMER SPECIFICS:
- SIDE-SCROLLING VIEW with parallax background layers (sky, mountains, trees).
- Draw the PLAYER as an animated character with idle, run, and jump poses (swap sprite frames).
- PLATFORMS should look like ground/stone/wood with textures drawn via patterns, not flat rectangles.
- Enemies should have distinct looks (e.g., slimes with bounce animation, flying bats with wing flaps).
- Coins should ROTATE (draw as ellipse that changes width over time) with sparkle particles.
- Implement wall-jumping, double-jumping, and coyote time for responsive controls.
- Scrolling camera that follows the player with smooth lerp.
- Death animation (player flashes and falls off screen).
- Level progression with increasing difficulty.""",

            "shooter": """SHOOTER SPECIFICS:
- Player ship with engine glow and exhaust particles.
- Enemy ships with distinct silhouettes (small fighters, medium cruisers, large bosses).
- Bullets should have TRAILS (glowing lines behind them).
- EXPLOSIONS with expanding circles, debris particles, and screen flash.
- Power-up drops: shield (bubble around ship), spread shot, rapid fire.
- Boss fights with health bars and attack patterns (bullet hell style).
- Scrolling starfield background with parallax star layers.
- Score multiplier for consecutive hits.""",

            "space_shooter": """SPACE SHOOTER SPECIFICS:
- Vertical or horizontal scrolling space shooter.
- Draw detailed ships with wings, cockpits, and engine glows using canvas paths.
- Animated starfield background with multiple parallax layers and nebula colors.
- Bullet types: laser beams (thin bright lines with glow), missiles (with smoke trail),
  spread shots.
- Asteroids that break into smaller pieces when shot.
- Shield power-ups with visible bubble effect.
- Boss enemies with multiple destructible parts and complex attack patterns.
- Screen-wide special weapon effects.""",

            "flappy": """FLAPPY BIRD SPECIFICS:
- Draw a PROPER BIRD with body, wing (animated flapping), eye, and beak — not a circle.
- Pipes should look like pipes: green gradient with caps, proper 3D-ish shading.
- Scrolling background with sky gradient, clouds, and distant city/trees.
- Ground with grass texture pattern scrolling at different speed.
- Bird should rotate based on velocity (nose up when flapping, nose down when falling).
- Smooth flap animation with wing position changing.
- Score displayed large and centered at top with outlined text.
- Screen flash white briefly on death.
- Increasing difficulty: pipes get closer together or gaps get smaller.""",

            "snake": """SNAKE GAME SPECIFICS:
- Draw the snake with a gradient-colored body, distinct head with eyes and tongue.
- Grid-based movement with smooth interpolation between cells.
- Food items that pulse/glow to attract attention.
- Snake body segments should have rounded corners and slight size variation.
- Trail effect as snake moves.
- Growing animation when eating.
- Wall or border with visible pattern.
- Speed increases as snake grows.
- Different food types worth different points with different colors.""",

            "puzzle": """PUZZLE GAME SPECIFICS:
- Clear, colorful game pieces with distinct shapes AND colors for accessibility.
- Smooth piece movement animations (slide, snap-to-grid).
- Match/clear effects: pieces shatter into colored particles, chain combos flash and shake.
- Score combo multiplier with big animated text ("COMBO x3!").
- Grid lines visible but subtle.
- Preview of next piece/move.
- Timer bar that changes color as time runs out.
- Satisfying clear sounds (ascending tones for combos).""",

            "rpg": """RPG SPECIFICS:
- Top-down view with tile-based movement.
- Character with walking animation (sprite frame cycling per direction).
- Enemies with unique looks and health bars above them.
- Combat: attack animation (slash effect), damage numbers floating up.
- Inventory/health display in a panel.
- NPCs with speech bubbles for dialogue.
- Treasure chests with opening animation.
- Different terrain types (grass, stone, water) drawn with pattern variations.
- XP bar and level-up effect (flash + particle burst).""",

            "fighting": """FIGHTING GAME SPECIFICS:
- Two fighters facing each other with distinct body shapes and colors.
- Draw fighters with proper proportions: head, torso, arms, legs.
- Attack animations: punch (arm extends), kick (leg extends), block (arms crossed).
- Health bars at top of screen with fighter names, round indicator.
- Hit effects: impact flash, hit sparks, knockback.
- Special move with charge-up glow and dramatic effect.
- Arena/stage background with floor and scenery.
- Combo counter for consecutive hits.
- Round-based gameplay (best of 3).""",

            "survival": """SURVIVAL/ROGUELIKE SPECIFICS:
- Top-down view with player in center, enemies approaching from all sides.
- Auto-attack mechanic or simple attack in facing direction.
- Wave counter and increasing enemy count/speed.
- XP orbs that float toward the player with a magnetic effect.
- Level-up screen with weapon/ability choices.
- Player health bar and XP bar at bottom.
- Enemies explode into particles on death.
- Different enemy types with visual distinctions (colors, sizes, shapes).
- Damage numbers floating above enemies.
- Screen gets more intense (redder vignette) as health drops.""",

            "tower_defense": """TOWER DEFENSE SPECIFICS:
- Top-down grid view with clear path for enemies.
- Towers drawn as distinct structures (turrets, magic towers, cannons).
- Enemy path highlighted or visible.
- Projectiles from towers to enemies with trail effects.
- Enemy health bars above them.
- Gold/resource counter for building towers.
- Wave indicator and countdown timer.
- Tower range shown as translucent circle on hover/select.
- Upgrade effects (tower gets bigger/changes color).""",

            "topdown": """TOP-DOWN GAME SPECIFICS:
- 8-directional movement with proper rotation toward movement direction.
- Draw player and enemies as detailed top-down sprites (body, head visible from above).
- Proper top-down environment: walls, floors, doors with shadows.
- Projectiles with trail effects.
- Enemy AI: pathfinding toward player, different attack patterns.
- Minimap in corner showing layout.
- Pickups with floating and glowing animation.""",
        }

        base = instructions.get(game_type, instructions.get("arcade", """ARCADE GAME SPECIFICS:
- Fast-paced, easy to learn, hard to master gameplay.
- Clear player character with proper sprite drawing (not just a rectangle).
- Enemies with distinct visual profiles.
- Collectibles with shine/glow animations.
- Increasing difficulty curve.
- High score tracking.
- Visual juice: screen shake, particles, flashes on every interaction."""))

        return base

    async def _generate_rich_html_game(
        self,
        prompt: str,
        design_doc: dict[str, Any],
        entities: list[dict[str, Any]],
        script_map: dict[str, str],
        asset_map: dict[str, dict],
        history: list[dict] | None = None,
    ) -> str:
        """Use Gemini to create a comprehensive HTML5 game informed by all agent outputs."""

        game_type = design_doc.get("game_type", "arcade")

        # Build entity descriptions with their behaviors from GDScript analysis
        entity_descriptions = []
        for entity in entities:
            ename = _safe_filename(entity["name"])
            script_code = script_map.get(ename, "")
            asset_data = asset_map.get(ename, {})
            spec = asset_data.get("spec", {}) if isinstance(asset_data, dict) else {}
            sprite_spec = spec.get("sprite", {}) if isinstance(spec, dict) else {}
            colors = sprite_spec.get("color_scheme", ["#4A90E2", "#ECF0F1"])
            shape = sprite_spec.get("shape", "rectangle")

            # Extract key behaviors from GDScript
            behaviors = []
            if "move_and_slide" in script_code:
                behaviors.append("physics-based movement")
            if "JUMP_VELOCITY" in script_code or "jump" in script_code.lower():
                behaviors.append("jumping")
            if "patrol" in script_code.lower() or "_direction" in script_code:
                behaviors.append("patrol AI")
            if "queue_free" in script_code:
                behaviors.append("collectible (disappears on contact)")
            if "gravity" in script_code.lower():
                behaviors.append("affected by gravity")

            entity_descriptions.append(
                f"  - {entity['name']} (type: {entity['type']}): "
                f"shape={shape}, colors={colors}, behaviors=[{', '.join(behaviors)}]"
            )

        entity_text = "\n".join(entity_descriptions)
        mechanics = ", ".join(design_doc.get("mechanics", ["standard"]))
        win_conditions = ", ".join(design_doc.get("win_conditions", ["Score points"]))

        # Visual style from design doc (if available)
        visual_style = design_doc.get("visual_style", {})
        theme = visual_style.get("theme", "modern")
        bg_color = visual_style.get("background", "#0a0a0a")
        primary_colors = visual_style.get("primary_colors", ["#4A90E2", "#E74C3C", "#F1C40F"])

        # Game-type specific rendering and gameplay instructions
        game_type_instructions = self._get_game_type_instructions(game_type, prompt)

        system = f"""You are an ELITE HTML5 game developer who creates POLISHED, VISUALLY IMPRESSIVE,
FULLY PLAYABLE games. You take great pride in making games that look and feel PROFESSIONAL.

== GAME DESIGN (from Design Agent) ==
Game type: {game_type}
Mechanics: {mechanics}
Win conditions: {win_conditions}
Summary: {design_doc.get('summary', 'A fun game')}
Visual theme: {theme}
Background color: {bg_color}
Color palette: {', '.join(primary_colors)}

== ENTITIES (from Script & Asset Agents) ==
{entity_text}

== GAME-TYPE SPECIFIC REQUIREMENTS ==
{game_type_instructions}

== VISUAL QUALITY REQUIREMENTS ==
1. DRAW PROPER SPRITES — NOT just colored rectangles! Use ctx.beginPath(), arcs, lines,
   gradients, and composite shapes to draw recognizable game objects:
   - Cars should look like cars (body, wheels, windshield, spoiler)
   - Characters should have heads, bodies, limbs, and eyes
   - Enemies should look menacing with distinct silhouettes
   - Coins/pickups should shine and animate (rotation, glow)
   - Backgrounds should have depth (parallax, gradient skies, terrain)
2. Use GRADIENTS (ctx.createLinearGradient / ctx.createRadialGradient) for polished visuals.
3. Add SHADOWS (ctx.shadowColor, ctx.shadowBlur) for depth.
4. Implement SMOOTH ANIMATIONS — easing functions, not sudden state changes.
5. Screen shake on impacts, flash effects on damage.
6. Draw proper TRAILS and PARTICLE EFFECTS for movement, explosions, collections.
7. Use GLOW EFFECTS (shadowBlur with bright colors) for power-ups and collectibles.
8. Render a PROPER HUD with styled score, health bars, and progress indicators.
9. Starfield / parallax scrolling backgrounds where appropriate.

== CORE REQUIREMENTS ==
1. Single HTML file with ALL CSS in <style> and ALL JS in <script>.
2. Use HTML5 Canvas for rendering — no DOM-based game objects.
3. COMPLETE game logic: player controls, enemy AI, collision detection, scoring, lives/health,
   game over, restart. The game MUST be fully playable with clear objectives.
4. requestAnimationFrame game loop with proper deltaTime.
5. Keyboard controls: Arrow keys / WASD + Space for action.
6. Font: font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif;
7. -webkit-font-smoothing: antialiased; on body
8. NO external libraries, CDNs, images, or assets. 100% self-contained.
9. Multiple levels or increasing difficulty over time.
10. Start screen with animated title, controls guide, and "Press SPACE to start".
11. Game over screen with final score and restart option.
12. Sound effects using Web Audio API (beeps, tones, noise bursts for different events).
13. Responsive canvas that fills the viewport.
14. At least 3 distinct particle effect types (explosion, trail, sparkle).
15. Smooth camera or viewport management where applicable.

== ORIGINAL USER REQUEST ==
{prompt}

Return ONLY the complete HTML document starting with <!DOCTYPE html> and ending with </html>.
Do NOT wrap in JSON. Do NOT add markdown fences. Return ONLY the raw HTML.
The game MUST be immediately playable, visually polished, and FUN when loaded in a browser."""

        history_text = self._format_history(history or [])
        full_prompt = f"{system}{history_text}\n\nUSER REQUEST: {prompt}"

        try:
            result = await provider_manager.generate(full_prompt, temperature=0.6)
            html = result.text.strip()
            # Strip markdown fences if present
            if html.startswith("```"):
                lines = html.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                html = "\n".join(lines).strip()
            # Validate it looks like HTML
            if "<!DOCTYPE" in html.upper() or "<html" in html.lower():
                return html
            # If Gemini returned JSON instead, try to extract
            doc = self._extract_json_object(html)
            if doc and "files" in doc and "index.html" in doc["files"]:
                return doc["files"]["index.html"]
            return self._self_contained_html_game(design_doc.get("game_type", "arcade"))
        except Exception as e:
            logger.warning("Rich HTML game generation failed: %s", e)
            return self._self_contained_html_game(design_doc.get("game_type", "arcade"))

    async def generate_complete_game(
        self,
        prompt: str,
        username: str,
        project_name: str,
        project_id: str,
        realtime: Any = None,
    ) -> GodotGenerateResult:
        """Orchestrate all agents to produce a complete Godot 4.x project.

        Phases:
          1. Design   — DesignAgent produces game_type, entities, mechanics
          2. Assets   — AssetAgent generates sprites in parallel + tileset + bg
          3. Scripts  — ScriptAgent generates .gd files in parallel
          4. Scenes   — SceneAgent generates .tscn files in parallel
          5. Assembly — main.tscn, project.godot, icon.svg, README.md
          6. Upload   — all files pushed to S3 under {username}/{project_name}/

        Args:
            prompt:       Natural-language game description from the user.
            username:     S3 path prefix (owner of the project).
            project_name: S3 path prefix (project folder name).
            project_id:   Used for WebSocket broadcasts only.
            realtime:     Optional RealtimeManager for progress events.

        Returns:
            GodotGenerateResult with S3 URLs, stats, and any non-fatal errors.
        """
        result = GodotGenerateResult()
        errors: list[str] = []

        # ── Phase 1: Design ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "design", "status": "running"})
        design_result = await self.generate_design(prompt)
        design_doc = design_result.payload
        result.design_doc = design_doc

        entities_raw = design_doc.get("entities", ["player"])
        entities = [_normalize_entity(e) for e in entities_raw]
        if not any(e["type"] in ("character", "player") for e in entities):
            entities.insert(0, _normalize_entity("Player"))

        await _emit(realtime, project_id, "godot_progress", {"phase": "design", "status": "complete"})

        # ── Phase 2: Assets ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "assets", "status": "running"})
        asset_tasks = [asset_agent.run(e, design_doc) for e in entities]
        asset_results = await asyncio.gather(*asset_tasks, return_exceptions=True)

        sprite_map: dict[str, dict] = {}
        for i, res in enumerate(asset_results):
            ename = _safe_filename(entities[i]["name"])
            if isinstance(res, Exception):
                errors.append(f"Asset failed for {ename}: {res}")
                sprite_map[ename] = {"png_b64": None}
            else:
                sprite_map[ename] = res

        tileset_b64 = await asset_agent.generate_tileset(design_doc)
        bg_b64 = await asset_agent.generate_background(design_doc)
        await _emit(realtime, project_id, "godot_progress", {"phase": "assets", "status": "complete"})

        # ── Phase 3: Scripts ───────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "scripts", "status": "running"})
        script_tasks = [script_agent.run(e, design_doc) for e in entities]
        script_results = await asyncio.gather(*script_tasks, return_exceptions=True)

        script_map: dict[str, str] = {}
        for i, res in enumerate(script_results):
            ename = _safe_filename(entities[i]["name"])
            if isinstance(res, Exception):
                errors.append(f"Script failed for {ename}: {res}")
                script_map[ename] = _fallback_script(entities[i])
            else:
                script_map[ename] = res

        await _emit(realtime, project_id, "godot_progress", {"phase": "scripts", "status": "complete"})

        # ── Phase 4: Scenes ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "scenes", "status": "running"})
        scene_tasks = [scene_agent.run(e, design_doc) for e in entities]
        scene_results = await asyncio.gather(*scene_tasks, return_exceptions=True)

        scene_map: dict[str, str] = {}
        for i, res in enumerate(scene_results):
            ename = _safe_filename(entities[i]["name"])
            if isinstance(res, Exception):
                errors.append(f"Scene failed for {ename}: {res}")
                scene_map[ename] = f'[gd_scene format=3]\n[node name="{ename}" type="Node2D"]\n'
            else:
                scene_map[ename] = res

        await _emit(realtime, project_id, "godot_progress", {"phase": "scenes", "status": "complete"})

        # ── Phase 5: Assembly ──────────────────────────────────────────────
        game_name = design_doc.get("game_type", "game").title() + " Game"
        project_config = _generate_project_config(game_name, design_doc.get("game_type", "arcade"))
        main_scene = _generate_main_scene(entities, design_doc.get("game_type", "arcade"))
        icon_svg = _generate_icon_svg()
        readme = _generate_readme(
            design_doc.get("game_type", "arcade"),
            design_doc.get("mechanics", []),
        )

        # ── Phase 6: Upload ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "upload", "status": "running"})
        file_urls: list[dict[str, str]] = []

        # Text files
        text_files = {
            "project.godot": project_config,
            "scenes/main.tscn": main_scene,
            "icon.svg": icon_svg,
            "README.md": readme,
        }
        for ename, content in scene_map.items():
            text_files[f"scenes/{ename}.tscn"] = content
        for ename, content in script_map.items():
            text_files[f"scripts/{ename}.gd"] = content

        for filename, content in text_files.items():
            try:
                r = await s3_storage.upload_file_content(username, project_name, filename, content)
                if r.get("url"):
                    file_urls.append({"filename": filename, "url": r["url"]})
            except Exception as e:
                errors.append(f"S3 upload failed for {filename}: {e}")
                logger.warning("S3 upload failed for %s: %s", filename, e)

        # Binary PNG assets
        for ename, asset_data in sprite_map.items():
            b64 = asset_data.get("png_b64")
            if not b64:
                continue
            try:
                raw_bytes = base64.b64decode(b64)
                r = await s3_storage.upload_bytes_content(
                    username, project_name, f"assets/{ename}.png", raw_bytes, "image/png"
                )
                if r.get("url"):
                    file_urls.append({"filename": f"assets/{ename}.png", "url": r["url"]})
            except Exception as e:
                errors.append(f"S3 PNG upload failed for {ename}: {e}")
                logger.warning("S3 PNG upload failed for %s: %s", ename, e)

        # Tileset and background
        for fname, b64 in [("assets/tileset.png", tileset_b64), ("assets/background.png", bg_b64)]:
            try:
                raw_bytes = base64.b64decode(b64)
                r = await s3_storage.upload_bytes_content(username, project_name, fname, raw_bytes, "image/png")
                if r.get("url"):
                    file_urls.append({"filename": fname, "url": r["url"]})
            except Exception as e:
                errors.append(f"S3 PNG upload failed for {fname}: {e}")

        result.file_urls = file_urls
        result.errors = errors
        result.stats = {
            "entities": len(entities),
            "scripts": len(script_map),
            "scenes": len(scene_map),
            "assets": len(sprite_map),
            "files_uploaded": len(file_urls),
        }
        result.status = "partial" if errors else "complete"

        await _emit(realtime, project_id, "godot_complete", {
            "status": result.status,
            "file_count": len(file_urls),
        })

        return result

    async def chat_reply(
        self,
        message: str,
        project: dict[str, Any],
        history: list[dict] | None = None,
    ) -> OrchestratorResult:
        system = "You are an expert game dev assistant. Respond concisely with practical next actions."
        lower = message.lower()
        project_name = project.get("name", "the project")

        if "optimiz" in lower:
            reply = (
                f"Optimization plan for {project_name}: reduce draw calls, pool enemies, "
                "and cap particle emitters during heavy scenes."
            )
            return OrchestratorResult(summary="reply", payload={"reply": reply}, usage=ProviderUsage())

        if any(k in lower for k in ("debug", "bug")):
            reply = (
                f"Debug checklist for {project_name}: verify collision layers, "
                "asset keys, and state transitions each frame."
            )
            return OrchestratorResult(summary="reply", payload={"reply": reply}, usage=ProviderUsage())

        history_text = self._format_history(history or [])
        full_prompt = f"{system}{history_text}\nCURRENT REQUEST: {message}"
        try:
            result = await provider_manager.generate(full_prompt, temperature=0.7)
            return OrchestratorResult(summary="reply", payload={"reply": result.text}, usage=result.usage)
        except Exception:
            reply = f'Assistant noted for {project_name}: "{message}". I can generate design/code updates or profiling guidance.'
            return OrchestratorResult(summary="reply", payload={"reply": reply}, usage=ProviderUsage())


ai_orchestrator = AIOrchestrator()
