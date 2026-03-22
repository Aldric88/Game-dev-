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
	add_to_group("enemies")
	var players = get_tree().get_nodes_in_group("player")
	if players.size() > 0:
		_player = players[0]

func _physics_process(delta: float) -> void:
	var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
	if not is_on_floor():
		velocity.y += gravity * delta

	_attack_timer -= delta
	_phase = 1 if health > max_health * 0.5 else 2

	if _player and global_position.distance_to(_player.global_position) < DETECTION_RANGE:
		_state = "chase"
		_direction = sign(_player.global_position.x - global_position.x)
		velocity.x = _direction * SPEED * (1.5 if _phase == 2 else 1.0)
	else:
		_state = "idle"
		velocity.x = _direction * SPEED * 0.5

	move_and_slide()
	if is_on_wall():
		_direction *= -1.0

func take_damage(amount: float) -> void:
	health -= amount
	if health <= 0:
		boss_defeated.emit()
		queue_free()
