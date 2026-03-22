"""Game-type inference and deterministic fallback design/code helpers.

These pure functions are used by AIOrchestrator when AI providers are unavailable
or return unusable output.
"""
from __future__ import annotations

from typing import Any
import json

from app.services.fallback_games import (
    _fallback_flappy_game,
    _fallback_platformer_game,
    _fallback_racing_game,
    _fallback_shooter_game,
    _fallback_snake_game,
)


def _normalize_entity(entity: Any) -> dict[str, Any]:
    """Coerce a string or partial dict entity entry to a full descriptor."""
    if isinstance(entity, dict):
        return {
            "name": entity.get("name", "Entity").strip().title(),
            "type": entity.get("type", "character"),
            "behaviors": entity.get("behaviors", entity.get("components", ["movement", "physics"])),
        }
    name = str(entity).strip().title()
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
    if any(k in lower for k in ("pipe", "obstacle", "wall", "platform", "ground")):
        return {"name": name, "type": "obstacle", "behaviors": ["static"]}
    if any(k in lower for k in ("score", "hud", "ui", "health", "timer", "display")):
        return {"name": name, "type": "ui", "behaviors": ["display"]}
    if any(k in lower for k in ("background", "sky", "scenery")):
        return {"name": name, "type": "environment", "behaviors": ["parallax"]}
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

def _infer_game_type(prompt: str) -> str:
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


def _infer_entities(prompt: str) -> list[str]:
    lower = prompt.lower()
    game_type = infer_game_type(prompt)

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


def _extract_json_object(text: str) -> dict[str, Any]:
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


def _fallback_design(prompt: str) -> dict[str, Any]:
    game_type = infer_game_type(prompt)
    entities = infer_entities(prompt)

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


def _fallback_code(prompt: str) -> dict[str, Any]:
    game_type = infer_game_type(prompt)
    html = get_html_fallback_game(game_type)
    return {
        "summary": "Generated starter HTML game using deterministic fallback.",
        "files": {"index.html": html},
        "entry_point": "index.html",
        "dependencies": [],
    }

def get_html_fallback_game(game_type: str) -> str:
    if game_type == "racing":
        return _fallback_racing_game()
    if game_type in ("flappy", "flappy_bird"):
        return _fallback_flappy_game()
    if game_type == "snake":
        return _fallback_snake_game()
    if game_type in ("shooter", "space_shooter"):
        return _fallback_shooter_game()
    return _fallback_platformer_game()

