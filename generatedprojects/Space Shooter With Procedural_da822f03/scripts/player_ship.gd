extends CharacterBody2D

const SPEED := 250.0
const SHOOT_COOLDOWN := 0.2

var _shoot_timer := 0.0

signal shoot_bullet(pos: Vector2, dir: Vector2)

func _ready() -> void:
	add_to_group("player")

func _physics_process(delta: float) -> void:
	var input_dir := Vector2.ZERO
	input_dir.x = Input.get_axis("move_left", "move_right")
	input_dir.y = Input.get_axis("jump", "move_left") * 0  # Use up/down if available

	if Input.is_action_pressed("jump"):
		input_dir.y = -1.0

	velocity = input_dir.normalized() * SPEED
	move_and_slide()

	# Clamp to screen
	var vp := get_viewport_rect().size
	global_position.x = clamp(global_position.x, 16, vp.x - 16)
	global_position.y = clamp(global_position.y, 16, vp.y - 16)

	# Shooting
	_shoot_timer -= delta
	if Input.is_action_pressed("jump") and _shoot_timer <= 0:
		_shoot_timer = SHOOT_COOLDOWN
		shoot_bullet.emit(global_position + Vector2(0, -20), Vector2.UP)
