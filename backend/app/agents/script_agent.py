"""ScriptAgent — generates GDScript 4.x source files for Godot entities.

The agent returns the full .gd file content as a plain string.
S3 upload is handled by the orchestrator, not here.
"""
from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent

# ─── Fallback scripts for common entity types ──────────────────────────────

_FALLBACK_PLAYER = """\
extends CharacterBody2D

const SPEED := 200.0
const JUMP_VELOCITY := -350.0
const ACCELERATION := 1200.0
const FRICTION := 800.0

var _coyote_frames := 0
var _jump_buffer := 0

func _ready() -> void:
\tadd_to_group("player")

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

_FALLBACK_BOSS = """\
extends CharacterBody2D

const SPEED := 60.0
const DETECTION_RANGE := 400.0

@export var max_health := 100.0
var health := max_health
var _direction := 1.0
var _state := "idle"
var _attack_timer := 0.0
var _phase := 1

signal boss_defeated

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

\t_attack_timer -= delta
\t_phase = 1 if health > max_health * 0.5 else 2

\tif _player and global_position.distance_to(_player.global_position) < DETECTION_RANGE:
\t\t_state = "chase"
\t\t_direction = sign(_player.global_position.x - global_position.x)
\t\tvelocity.x = _direction * SPEED * (1.5 if _phase == 2 else 1.0)
\telse:
\t\t_state = "idle"
\t\tvelocity.x = _direction * SPEED * 0.5

\tmove_and_slide()
\tif is_on_wall():
\t\t_direction *= -1.0

func take_damage(amount: float) -> void:
\thealth -= amount
\tif health <= 0:
\t\tboss_defeated.emit()
\t\tqueue_free()
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

func _ready() -> void:
\tadd_to_group("player")

func _physics_process(delta: float) -> void:
\tvar throttle := 0.0
\tif InputMap.has_action("move_up"):
\t\tthrottle = Input.get_axis("move_down", "move_up")
\telse:
\t\tif Input.is_action_pressed("jump"):
\t\t\tthrottle = 1.0

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

\trotation += _steer_angle * (_speed / MAX_SPEED)
\tvelocity = Vector2.UP.rotated(rotation) * _speed
\tmove_and_slide()
"""

_FALLBACK_FLAPPY_BIRD = """\
extends CharacterBody2D

const FLAP_FORCE := -300.0
const GRAVITY := 800.0
const MAX_FALL_SPEED := 400.0
const ROTATION_SPEED := 3.0

var _alive := true

signal died

func _ready() -> void:
\tadd_to_group("player")

func _physics_process(delta: float) -> void:
\tif not _alive:
\t\treturn

\tvelocity.y += GRAVITY * delta
\tvelocity.y = min(velocity.y, MAX_FALL_SPEED)

\tif Input.is_action_just_pressed("jump"):
\t\tvelocity.y = FLAP_FORCE

\t# Rotate based on velocity
\tif velocity.y < 0:
\t\trotation = lerp(rotation, -0.4, ROTATION_SPEED * delta)
\telse:
\t\trotation = lerp(rotation, 1.2, ROTATION_SPEED * delta * 0.5)

\tmove_and_slide()

\t# Check screen bounds
\tif global_position.y > get_viewport_rect().size.y + 50:
\t\t_die()

func _die() -> void:
\tif _alive:
\t\t_alive = false
\t\tdied.emit()
"""

_FALLBACK_PIPE = """\
extends StaticBody2D

const SCROLL_SPEED := 150.0
const GAP_SIZE := 150.0

var _active := true

func _ready() -> void:
\tadd_to_group("obstacles")

func _physics_process(delta: float) -> void:
\tif _active:
\t\tposition.x -= SCROLL_SPEED * delta
\t\tif position.x < -100:
\t\t\tqueue_free()
"""

_FALLBACK_GROUND = """\
extends StaticBody2D

const SCROLL_SPEED := 150.0

func _ready() -> void:
\tadd_to_group("world")

func _physics_process(_delta: float) -> void:
\tpass
"""

_FALLBACK_BACKGROUND = """\
extends Node2D

@export var scroll_speed := 50.0
var _offset := 0.0

func _process(delta: float) -> void:
\t_offset += scroll_speed * delta
\tposition.x = -fmod(_offset, get_viewport_rect().size.x)
"""

_FALLBACK_SCORE_UI = """\
extends Node2D

var score := 0

func _ready() -> void:
\tadd_to_group("ui")

func _process(_delta: float) -> void:
\tqueue_redraw()

func _draw() -> void:
\tvar font := ThemeDB.fallback_font
\tdraw_string(font, Vector2(10, 30), "Score: " + str(score), HORIZONTAL_ALIGNMENT_LEFT, -1, 24, Color.WHITE)

func add_score(amount: int) -> void:
\tscore += amount
"""

_FALLBACK_GAME_OVER_UI = """\
extends Node2D

var _visible := false

func _ready() -> void:
\tadd_to_group("ui")
\tvisible = false

func show_game_over() -> void:
\t_visible = true
\tvisible = true
\tqueue_redraw()

func _draw() -> void:
\tif not _visible:
\t\treturn
\tvar font := ThemeDB.fallback_font
\tvar center := get_viewport_rect().size / 2
\tdraw_string(font, center - Vector2(80, 0), "GAME OVER", HORIZONTAL_ALIGNMENT_CENTER, -1, 36, Color.RED)
\tdraw_string(font, center + Vector2(-100, 40), "Press SPACE to restart", HORIZONTAL_ALIGNMENT_CENTER, -1, 18, Color.WHITE)

func _input(event: InputEvent) -> void:
\tif _visible and event.is_action_pressed("jump"):
\t\tget_tree().reload_current_scene()
"""

_FALLBACK_PROJECTILE = """\
extends Area2D

const SPEED := 500.0
const DAMAGE := 10.0
const LIFETIME := 3.0

var direction := Vector2.RIGHT
var _timer := 0.0

func _ready() -> void:
\tadd_to_group("projectiles")
\tbody_entered.connect(_on_body_entered)

func _physics_process(delta: float) -> void:
\tposition += direction * SPEED * delta
\t_timer += delta
\tif _timer >= LIFETIME:
\t\tqueue_free()

func _on_body_entered(body: Node2D) -> void:
\tif body.is_in_group("enemies") and body.has_method("take_damage"):
\t\tbody.take_damage(DAMAGE)
\tqueue_free()
"""

_FALLBACK_SHIP = """\
extends CharacterBody2D

const SPEED := 250.0
const SHOOT_COOLDOWN := 0.2

var _shoot_timer := 0.0

signal shoot_bullet(pos: Vector2, dir: Vector2)

func _ready() -> void:
\tadd_to_group("player")

func _physics_process(delta: float) -> void:
\tvar input_dir := Vector2.ZERO
\tinput_dir.x = Input.get_axis("move_left", "move_right")
\tinput_dir.y = Input.get_axis("jump", "move_left") * 0  # Use up/down if available

\tif Input.is_action_pressed("jump"):
\t\tinput_dir.y = -1.0

\tvelocity = input_dir.normalized() * SPEED
\tmove_and_slide()

\t# Clamp to screen
\tvar vp := get_viewport_rect().size
\tglobal_position.x = clamp(global_position.x, 16, vp.x - 16)
\tglobal_position.y = clamp(global_position.y, 16, vp.y - 16)

\t# Shooting
\t_shoot_timer -= delta
\tif Input.is_action_pressed("jump") and _shoot_timer <= 0:
\t\t_shoot_timer = SHOOT_COOLDOWN
\t\tshoot_bullet.emit(global_position + Vector2(0, -20), Vector2.UP)
"""

_FALLBACK_OBSTACLE = """\
extends StaticBody2D

func _ready() -> void:
\tadd_to_group("obstacles")
"""

_FALLBACK_PLATFORM = """\
extends StaticBody2D

@export var is_moving := false
@export var move_distance := 100.0
@export var move_speed := 50.0

var _start_pos := Vector2.ZERO
var _direction := 1.0

func _ready() -> void:
\tadd_to_group("world")
\t_start_pos = position

func _physics_process(delta: float) -> void:
\tif is_moving:
\t\tposition.x += move_speed * _direction * delta
\t\tif abs(position.x - _start_pos.x) > move_distance:
\t\t\t_direction *= -1.0
"""

_FALLBACK_SNAKE_HEAD = """\
extends CharacterBody2D

const GRID_SIZE := 32
const MOVE_INTERVAL := 0.15

var direction := Vector2.RIGHT
var _move_timer := 0.0
var _body_segments: Array[Vector2] = []
var _grow_pending := 0

signal ate_food
signal died

func _ready() -> void:
\tadd_to_group("player")
\t_body_segments.append(global_position)

func _physics_process(delta: float) -> void:
\t# Input
\tif Input.is_action_pressed("move_right") and direction != Vector2.LEFT:
\t\tdirection = Vector2.RIGHT
\telif Input.is_action_pressed("move_left") and direction != Vector2.RIGHT:
\t\tdirection = Vector2.LEFT
\telif Input.is_action_pressed("jump") and direction != Vector2.DOWN:
\t\tdirection = Vector2.UP
\telif Input.is_action_pressed("move_down") and direction != Vector2.UP:
\t\tdirection = Vector2.DOWN

\t_move_timer += delta
\tif _move_timer >= MOVE_INTERVAL:
\t\t_move_timer = 0.0
\t\t_move_step()

func _move_step() -> void:
\tvar old_pos := global_position
\tglobal_position += direction * GRID_SIZE

\t_body_segments.insert(0, old_pos)
\tif _grow_pending > 0:
\t\t_grow_pending -= 1
\telse:
\t\t_body_segments.pop_back()

\t# Wall collision
\tvar vp := get_viewport_rect().size
\tif global_position.x < 0 or global_position.x >= vp.x or global_position.y < 0 or global_position.y >= vp.y:
\t\tdied.emit()

\t# Self collision
\tif global_position in _body_segments:
\t\tdied.emit()

\tqueue_redraw()

func grow() -> void:
\t_grow_pending += 1
\tate_food.emit()
"""

_FALLBACK_FOOD = """\
extends Area2D

var _hover_time := 0.0

func _ready() -> void:
\tadd_to_group("collectibles")
\tbody_entered.connect(_on_body_entered)
\t_randomize_position()

func _process(delta: float) -> void:
\t_hover_time += delta
\tscale = Vector2.ONE * (1.0 + sin(_hover_time * 4.0) * 0.1)

func _on_body_entered(body: Node2D) -> void:
\tif body.is_in_group("player"):
\t\tif body.has_method("grow"):
\t\t\tbody.grow()
\t\t_randomize_position()

func _randomize_position() -> void:
\tvar vp := get_viewport_rect().size
\tglobal_position = Vector2(
\t\tsnapped(randf_range(32, vp.x - 32), 32),
\t\tsnapped(randf_range(32, vp.y - 32), 32)
\t)
"""

_FALLBACK_WALL = """\
extends StaticBody2D

func _ready() -> void:
\tadd_to_group("world")
"""

_FALLBACK_HEALTH_UI = """\
extends Node2D

var max_health := 100.0
var current_health := 100.0

func _ready() -> void:
\tadd_to_group("ui")

func _process(_delta: float) -> void:
\tqueue_redraw()

func _draw() -> void:
\tvar bar_width := 200.0
\tvar bar_height := 20.0
\tvar ratio := current_health / max_health
\tdraw_rect(Rect2(0, 0, bar_width, bar_height), Color(0.3, 0.3, 0.3))
\tdraw_rect(Rect2(0, 0, bar_width * ratio, bar_height), Color(0.2, 0.8, 0.2) if ratio > 0.5 else Color(0.8, 0.2, 0.2))

func set_health(value: float) -> void:
\tcurrent_health = clamp(value, 0, max_health)
"""

_FALLBACK_AI_OPPONENT = """\
extends CharacterBody2D

const SPEED := 60.0
var _direction := 1.0
var _timer := 0.0

func _ready() -> void:
\tadd_to_group("enemies")

func _physics_process(delta: float) -> void:
\tvar gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta

\t_timer += delta
\tif _timer > 2.0:
\t\t_direction *= -1.0
\t\t_timer = 0.0

\tvelocity.x = _direction * SPEED
\tmove_and_slide()

\tif is_on_wall():
\t\t_direction *= -1.0
\t\t_timer = 0.0
"""

_FALLBACK_SHIELD = """\
extends Area2D

signal collected

var _hover_time := 0.0

func _ready() -> void:
\tadd_to_group("collectibles")
\tbody_entered.connect(_on_body_entered)

func _process(delta: float) -> void:
\t_hover_time += delta
\tposition.y += sin(_hover_time * 3.0) * 0.3

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

# ─── Keyword groups for fallback matching ──────────────────────────────────

_PLAYER_KEYWORDS = ("player", "hero", "character", "protagonist")
_ENEMY_KEYWORDS = ("enemy", "foe", "monster", "villain", "opponent", "alien", "horde", "cruiser")
_BOSS_KEYWORDS = ("boss",)
_COLLECT_KEYWORDS = ("coin", "collect", "pickup", "item", "gem", "star", "goal", "treasure", "potion", "orb")
_POWER_KEYWORDS = ("power", "boost", "speed", "damage", "multiplier")
_CAR_KEYWORDS = ("car", "vehicle", "racer", "kart", "truck")
_BIRD_KEYWORDS = ("bird", "flappy")
_PIPE_KEYWORDS = ("pipe", "obstacle column")
_SNAKE_KEYWORDS = ("snake",)
_FOOD_KEYWORDS = ("food", "apple", "pellet")
_SHIP_KEYWORDS = ("ship", "spaceship", "fighter", "plane")
_BULLET_KEYWORDS = ("bullet", "projectile", "laser", "missile")
_GROUND_KEYWORDS = ("ground", "floor")
_BACKGROUND_KEYWORDS = ("background", "sky", "scenery", "nebula", "dust", "space")
_SCORE_KEYWORDS = ("score", "display", "hud", "counter")
_HEALTH_KEYWORDS = ("health", "hp", "life")
_GAMEOVER_KEYWORDS = ("game over", "game_over", "gameover", "death screen")
_WALL_KEYWORDS = ("wall", "barrier", "border")
_PLATFORM_KEYWORDS = ("platform",)
_OBSTACLE_KEYWORDS = ("obstacle", "hazard", "trap", "asteroid")
_SHIELD_KEYWORDS = ("shield",)
_WEAPON_KEYWORDS = ("weapon", "gun", "sword")
_AI_KEYWORDS = ("ai opponent", "ai car", "ai_opponent", "cpu")


def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword appears as a whole word (not substring) in text."""
    import re
    return bool(re.search(r'(?:^|[\s_\-])' + re.escape(keyword) + r'(?:[\s_\-]|$)', text))


def _any_word_match(keywords: tuple, text: str) -> bool:
    """Check if any keyword appears as a whole word in text."""
    return any(_word_match(k, text) for k in keywords)


def _fallback_for(entity: dict[str, Any]) -> str:
    """Select the best fallback script based on entity name and type."""
    name = entity.get("name", "").lower()
    etype = entity.get("type", "").lower()
    combined = name + " " + etype

    # Order matters — more specific checks first.
    # Use word-boundary matching to prevent substring collisions
    # (e.g. "background" must NOT match "ground").
    if _any_word_match(_BOSS_KEYWORDS, combined):
        return _FALLBACK_BOSS
    if _any_word_match(_GAMEOVER_KEYWORDS, combined):
        return _FALLBACK_GAME_OVER_UI
    if _any_word_match(_BIRD_KEYWORDS, combined):
        return _FALLBACK_FLAPPY_BIRD
    if _any_word_match(_PIPE_KEYWORDS, combined) and "obstacle" in combined:
        return _FALLBACK_PIPE
    if _any_word_match(_SNAKE_KEYWORDS, combined) and ("head" in combined or "player" in etype):
        return _FALLBACK_SNAKE_HEAD
    if _any_word_match(_FOOD_KEYWORDS, combined):
        return _FALLBACK_FOOD
    if _any_word_match(_BULLET_KEYWORDS, combined):
        return _FALLBACK_PROJECTILE
    if _any_word_match(_SHIP_KEYWORDS, combined) and ("player" in etype or "character" in etype):
        return _FALLBACK_SHIP
    if _any_word_match(_CAR_KEYWORDS, combined) and ("player" in etype or "vehicle" in etype):
        return _FALLBACK_CAR
    if _any_word_match(_AI_KEYWORDS, combined):
        return _FALLBACK_AI_OPPONENT
    if _any_word_match(_SHIELD_KEYWORDS, combined):
        return _FALLBACK_SHIELD
    if _any_word_match(_POWER_KEYWORDS, combined) or _any_word_match(_COLLECT_KEYWORDS, combined):
        return _FALLBACK_COLLECTIBLE
    if _any_word_match(_HEALTH_KEYWORDS, combined) and "ui" in etype:
        return _FALLBACK_HEALTH_UI
    if _any_word_match(_SCORE_KEYWORDS, combined) or "ui" in etype:
        return _FALLBACK_SCORE_UI
    # Background MUST be checked before ground (substring collision)
    if _any_word_match(_BACKGROUND_KEYWORDS, combined):
        return _FALLBACK_BACKGROUND
    if _any_word_match(_GROUND_KEYWORDS, combined):
        return _FALLBACK_GROUND
    if _any_word_match(_WALL_KEYWORDS, combined):
        return _FALLBACK_WALL
    if _any_word_match(_PLATFORM_KEYWORDS, combined):
        return _FALLBACK_PLATFORM
    if _any_word_match(_OBSTACLE_KEYWORDS, combined):
        return _FALLBACK_OBSTACLE
    if _any_word_match(_ENEMY_KEYWORDS, combined):
        return _FALLBACK_ENEMY
    if _any_word_match(_SHIP_KEYWORDS, combined):
        return _FALLBACK_SHIP
    if _any_word_match(_CAR_KEYWORDS, combined):
        return _FALLBACK_CAR
    if _any_word_match(_PLAYER_KEYWORDS, combined):
        return _FALLBACK_PLAYER
    if _word_match("pipe", combined):
        return _FALLBACK_PIPE
    if "environment" in etype:
        return _FALLBACK_BACKGROUND
    if "obstacle" in etype:
        return _FALLBACK_OBSTACLE
    if "trigger" in etype:
        return _FALLBACK_COLLECTIBLE
    return _FALLBACK_GENERIC


_SYSTEM_PROMPT = """\
You are a Godot 4.x GDScript expert who writes PRODUCTION-QUALITY game scripts.
Generate a complete, functional GDScript file for one game entity.
Return ONLY valid GDScript code — no markdown fences, no explanations.

CRITICAL Requirements:
- Correct `extends` statement (CharacterBody2D, Area2D, StaticBody2D, RigidBody2D, or Node2D).
- Godot 4.x syntax: typed variables, @export, @onready, signals.
- Physics bodies MUST call move_and_slide() with NO arguments (Godot 4.x).
- Movement: use Input.get_axis("move_left", "move_right") for horizontal.
- Gravity: read from ProjectSettings.get_setting("physics/2d/default_gravity").
- Player entities: add_to_group("player") in _ready(). Implement responsive controls
  with acceleration/deceleration. Include coyote time and jump buffering.
- Enemy entities: add_to_group("enemies") in _ready(). Implement AI with patrol + chase
  behavior. Use state machine pattern.
- Collectible entities: extend Area2D, connect body_entered signal in _ready(),
  emit a signal and call queue_free() when touched by player group.
- Racing/car entities: add_to_group("player") in _ready(). Implement acceleration,
  braking, steering, and drift mechanics.
- Boss entities: add_to_group("enemies") in _ready(). Implement health, attack phases,
  and a take_damage(amount) method.
- UI/Score entities: extend Node2D. Use _draw() with draw_string() for text.
- Background entities: extend Node2D. Implement parallax scrolling.
- Projectile entities: extend Area2D. Move in a direction, destroy on hit or timeout.

ABSOLUTELY DO NOT:
- Use preload() or load() to reference ANY external .tscn, .gd, or .tres files.
- Reference res://bullet.tscn, res://projectile.tscn, res://missile.tscn or similar.
- Use inner classes (class Foo extends Bar inside the script).
- Use Projectile.new() or any class instantiation for scenes.
- Reference nodes that don't exist in the scene tree yet.

Instead of loading external scenes for bullets/projectiles, emit a signal like:
  signal shoot_bullet(pos: Vector2, dir: Vector2)
  shoot_bullet.emit(global_position, Vector2.UP)

The main scene will handle connecting signals to spawn logic.

Return ONLY the GDScript source — nothing else.
"""


class ScriptAgent(BaseAgent):
    """Generates a Godot 4.x GDScript file for one game entity."""

    temperature: float = 0.4

    async def run(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> str:
        """Return .gd file content as a plain string."""
        prompt = self._create_prompt(entity, design_doc)
        try:
            raw = await self.generate(prompt)
            code = self._strip_fences(raw)
            if code.strip().startswith("extends"):
                code = self._sanitize_script(code)
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

    @staticmethod
    def _sanitize_script(code: str) -> str:
        """Fix common AI-generated GDScript mistakes."""
        import re
        lines = code.split("\n")
        cleaned = []
        for line in lines:
            # Remove any preload/load of external .tscn/.gd/.tres files
            if re.search(r'(preload|load)\s*\(\s*"res://', line):
                # Comment it out instead of removing, to preserve line structure
                cleaned.append("# REMOVED: " + line.lstrip())
                continue
            # Fix move_and_slide with arguments (Godot 4.x takes no args)
            line = re.sub(r'move_and_slide\s*\([^)]+\)', 'move_and_slide()', line)
            cleaned.append(line)
        return "\n".join(cleaned)


script_agent = ScriptAgent()
