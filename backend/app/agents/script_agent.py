"""ScriptAgent — generates GDScript 4.x source files for Godot entities.

The agent returns the full .gd file content as a plain string.
S3 upload is handled by the orchestrator, not here.
"""
from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent

_FALLBACK_PLAYER = """\
extends CharacterBody2D

const SPEED := 150.0
const JUMP_VELOCITY := -300.0

func _physics_process(delta: float) -> void:
\tvar gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\tif Input.is_action_just_pressed("jump") and is_on_floor():
\t\tvelocity.y = JUMP_VELOCITY
\tvar direction := Input.get_axis("move_left", "move_right")
\tvelocity.x = direction * SPEED
\tmove_and_slide()
"""

_FALLBACK_ENEMY = """\
extends CharacterBody2D

const SPEED := 60.0
var _direction := 1.0

func _physics_process(delta: float) -> void:
\tvar gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\tvelocity.x = _direction * SPEED
\tmove_and_slide()
\tif is_on_wall():
\t\t_direction *= -1.0
"""

_FALLBACK_COLLECTIBLE = """\
extends Area2D

signal collected

func _ready() -> void:
\tbody_entered.connect(_on_body_entered)

func _on_body_entered(body: Node2D) -> void:
\tif body.is_in_group("player"):
\t\tcollected.emit()
\t\tqueue_free()
"""

_FALLBACK_GENERIC = """\
extends Node2D

func _ready() -> void:
\tpass
"""

_PLAYER_KEYWORDS = ("player", "hero", "character", "protagonist")
_ENEMY_KEYWORDS = ("enemy", "foe", "monster", "boss", "villain")
_COLLECT_KEYWORDS = ("coin", "collect", "pickup", "item", "gem", "star", "goal")


def _fallback_for(entity: dict[str, Any]) -> str:
    name = entity.get("name", "").lower()
    etype = entity.get("type", "").lower()
    combined = name + " " + etype
    if any(k in combined for k in _COLLECT_KEYWORDS):
        return _FALLBACK_COLLECTIBLE
    if any(k in combined for k in _ENEMY_KEYWORDS):
        return _FALLBACK_ENEMY
    if any(k in combined for k in _PLAYER_KEYWORDS):
        return _FALLBACK_PLAYER
    return _FALLBACK_GENERIC


_SYSTEM_PROMPT = """\
You are a Godot 4.x GDScript expert.
Generate a complete, functional GDScript file for one game entity.
Return ONLY valid GDScript code — no markdown fences, no explanations.

Requirements:
- Correct `extends` statement (CharacterBody2D, Area2D, StaticBody2D, or Node2D).
- Godot 4.x syntax: typed variables, @export, signals.
- Physics bodies: use move_and_slide(), not move_and_collide().
- Movement: use Input.get_axis("move_left", "move_right").
- Gravity: read from ProjectSettings.get_setting("physics/2d/default_gravity").
- Player entities: implement WASD / arrow key movement and jump.
- Enemy entities: implement simple patrol (reverse on wall/edge).
- Collectible entities (coins, items, goals): extend Area2D, emit a signal and
  call queue_free() when touched by the player group.
- Do NOT reference external scenes or scripts.
- Return ONLY the GDScript source — nothing else.
"""


class ScriptAgent(BaseAgent):
    """Generates a Godot 4.x GDScript file for one game entity."""

    temperature: float = 0.4

    async def run(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> str:
        """Return .gd file content as a plain string.

        Args:
            entity:     Entity descriptor, e.g.
                        {"name": "Player", "type": "character", "behaviors": [...]}
            design_doc: Full design document from DesignAgent.

        Returns:
            Complete GDScript source ready for S3 upload.
        """
        prompt = self._create_prompt(entity, design_doc)
        try:
            raw = await self.generate(prompt)
            code = self._strip_fences(raw)
            if code.strip().startswith("extends"):
                return code
            return _fallback_for(entity)
        except Exception:
            return _fallback_for(entity)

    def _create_prompt(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> str:
        name = entity.get("name", "Entity")
        etype = entity.get("type", "character")
        behaviors = ", ".join(entity.get("behaviors", []) or entity.get("components", []))
        game_type = design_doc.get("game_type", "arcade")
        mechanics = ", ".join(design_doc.get("mechanics", []))

        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Entity name: {name}\n"
            f"Entity type: {etype}\n"
            f"Behaviors: {behaviors or 'none'}\n"
            f"Game type: {game_type}\n"
            f"Game mechanics: {mechanics or 'standard'}\n\n"
            f"Generate the complete GDScript for {name}."
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove ```gdscript ... ``` or ``` ... ``` fences if present."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text


script_agent = ScriptAgent()
