"""ScriptAgent — generates GDScript 4.x source files for Godot entities.

The agent returns the full .gd file content as a plain string.
S3 upload is handled by the orchestrator, not here.
"""
from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent

_FALLBACK_PLAYER = """\
extends CharacterBody2D

const SPEED := 200.0
const JUMP_VELOCITY := -350.0
const ACCELERATION := 1200.0
const FRICTION := 800.0

var _coyote_frames := 0
var _jump_buffer := 0

func _physics_process(delta: float) -> void:
\tvar gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\t\t_coyote_frames -= 1
\telse:
\t\t_coyote_frames = 6

\tif Input.is_action_just_pressed("jump"):
\t\t_jump_buffer = 8

\tif _jump_buffer > 0 and _coyote_frames > 0:
\t\tvelocity.y = JUMP_VELOCITY
\t\t_jump_buffer = 0
\t\t_coyote_frames = 0

\t_jump_buffer -= 1

\tvar direction := Input.get_axis("move_left", "move_right")
\tif direction:
\t\tvelocity.x = move_toward(velocity.x, direction * SPEED, ACCELERATION * delta)
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, FRICTION * delta)
\tmove_and_slide()
"""

_FALLBACK_ENEMY = """\
extends CharacterBody2D

const SPEED := 80.0
const DETECTION_RANGE := 200.0
var _direction := 1.0
var _state := "patrol"

@onready var _player: Node2D = null

func _ready() -> void:
\tadd_to_group("enemies")
\tvar players = get_tree().get_nodes_in_group("player")
\tif players.size() > 0:
\t\t_player = players[0]

func _physics_process(delta: float) -> void:
\tvar gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta

\tif _player and global_position.distance_to(_player.global_position) < DETECTION_RANGE:
\t\t_state = "chase"
\t\t_direction = sign(_player.global_position.x - global_position.x)
\telse:
\t\t_state = "patrol"

\tvelocity.x = _direction * SPEED
\tmove_and_slide()

\tif is_on_wall():
\t\t_direction *= -1.0
"""

_FALLBACK_COLLECTIBLE = """\
extends Area2D

signal collected

var _hover_time := 0.0

func _ready() -> void:
\tbody_entered.connect(_on_body_entered)
\tadd_to_group("collectibles")

func _process(delta: float) -> void:
\t_hover_time += delta
\tposition.y += sin(_hover_time * 3.0) * 0.3

func _on_body_entered(body: Node2D) -> void:
\tif body.is_in_group("player"):
\t\tcollected.emit()
\t\tqueue_free()
"""

_FALLBACK_CAR = """\
extends CharacterBody2D

const MAX_SPEED := 400.0
const ACCELERATION := 200.0
const BRAKE_FORCE := 300.0
const TURN_SPEED := 2.5
const DRIFT_FACTOR := 0.9
const FRICTION := 50.0

var _speed := 0.0
var _steer_angle := 0.0
var _is_drifting := false

func _physics_process(delta: float) -> void:
\tvar throttle := Input.get_axis("move_down", "move_up") if has_action("move_up") else 0.0
\tif Input.is_action_pressed("move_right"):
\t\t_steer_angle = TURN_SPEED * delta
\telif Input.is_action_pressed("move_left"):
\t\t_steer_angle = -TURN_SPEED * delta
\telse:
\t\t_steer_angle = 0.0

\tif throttle > 0:
\t\t_speed = min(_speed + ACCELERATION * delta, MAX_SPEED)
\telif throttle < 0:
\t\t_speed = max(_speed - BRAKE_FORCE * delta, -MAX_SPEED * 0.3)
\telse:
\t\t_speed = move_toward(_speed, 0, FRICTION * delta)

\tif Input.is_action_pressed("jump"):
\t\t_is_drifting = true
\t\t_speed *= DRIFT_FACTOR
\telse:
\t\t_is_drifting = false

\trotation += _steer_angle * (_speed / MAX_SPEED)
\tvelocity = Vector2.UP.rotated(rotation) * _speed
\tmove_and_slide()

func has_action(action: String) -> bool:
\treturn InputMap.has_action(action)
"""

_FALLBACK_GENERIC = """\
extends Node2D

func _ready() -> void:
\tpass
"""

_PLAYER_KEYWORDS = ("player", "hero", "character", "protagonist", "fighter")
_ENEMY_KEYWORDS = ("enemy", "foe", "monster", "boss", "villain", "opponent", "alien", "horde")
_COLLECT_KEYWORDS = ("coin", "collect", "pickup", "item", "gem", "star", "goal", "treasure", "potion", "orb", "power")
_CAR_KEYWORDS = ("car", "vehicle", "racer", "kart", "truck")


def _fallback_for(entity: dict[str, Any]) -> str:
    name = entity.get("name", "").lower()
    etype = entity.get("type", "").lower()
    combined = name + " " + etype
    if any(k in combined for k in _CAR_KEYWORDS):
        return _FALLBACK_CAR
    if any(k in combined for k in _COLLECT_KEYWORDS):
        return _FALLBACK_COLLECTIBLE
    if any(k in combined for k in _ENEMY_KEYWORDS):
        return _FALLBACK_ENEMY
    if any(k in combined for k in _PLAYER_KEYWORDS):
        return _FALLBACK_PLAYER
    return _FALLBACK_GENERIC


_SYSTEM_PROMPT = """\
You are a Godot 4.x GDScript expert who writes PRODUCTION-QUALITY game scripts.
Generate a complete, functional GDScript file for one game entity.
Return ONLY valid GDScript code — no markdown fences, no explanations.

Requirements:
- Correct `extends` statement (CharacterBody2D, Area2D, StaticBody2D, RigidBody2D, or Node2D).
- Godot 4.x syntax: typed variables, @export, @onready, signals.
- Physics bodies: use move_and_slide(), not move_and_collide().
- Movement: use Input.get_axis("move_left", "move_right") for horizontal.
- Gravity: read from ProjectSettings.get_setting("physics/2d/default_gravity").
- Player entities: implement responsive controls with acceleration/deceleration.
  Include coyote time (allow jump a few frames after leaving edge) and jump buffering.
- Enemy entities: implement AI with patrol + chase behavior (detect player in range).
  Use state machine pattern (patrol, chase, attack states).
- Collectible entities (coins, items, goals): extend Area2D, emit a signal and
  call queue_free() when touched by the player group. Add hover/bob animation.
- Racing/car entities: implement acceleration, braking, steering based on speed,
  drift mechanic, and track friction.
- Shooting entities: implement bullet spawning, fire rate, ammo management.
- Boss entities: implement health, attack phases, and vulnerability windows.
- Add entities to appropriate groups ("player", "enemies", "collectibles").
- Do NOT reference external scenes, scripts, or non-existent resources.
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
