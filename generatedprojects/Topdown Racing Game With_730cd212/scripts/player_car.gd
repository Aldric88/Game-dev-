extends CharacterBody2D

@export var acceleration: float = 200.0
@export var braking_force: float = 300.0
@export var max_speed: float = 400.0
@export var rotation_speed: float = 3.0
@export var drift_rotation_multiplier: float = 0.5
@export var drift_speed_multiplier: float = 0.8
@export var jump_force: float = 400.0
@export var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
@export var friction: float = 10.0

signal item_collected(item_name: String)
signal lap_completed()

var speed: float = 0.0
var is_drifting: bool = false
var velocity: Vector2 = Vector2.ZERO
var laps: int = 0

func _physics_process(delta: float) -> void:
	# Acceleration and Braking
	var acceleration_input: float = Input.get_axis("brake", "accelerate")
	if acceleration_input > 0:
		speed = min(speed + acceleration * delta, max_speed)
	elif acceleration_input < 0:
		speed = max(speed - braking_force * delta, 0.0)
	else:
		speed = max(speed - friction * delta, 0.0)

	# Steering
	var steer_direction: float = Input.get_axis("steer_left", "steer_right")
	var rotation_amount: float = steer_direction * rotation_speed * delta
	if is_drifting:
		rotation_amount *= drift_rotation_multiplier
	rotate(rotation_amount)

	# Movement
	var forward_direction: Vector2 = Vector2(1, 0).rotated(rotation)
	velocity = forward_direction * speed

	# Drifting
	if Input.is_action_pressed("drift"):
		is_drifting = true
		speed *= drift_speed_multiplier
	else:
		is_drifting = false

	# Jumping (Example, can be modified for racing)
	if is_on_floor() and Input.is_action_just_pressed("jump"):
		velocity.y = -jump_force

	# Gravity
	if not is_on_floor():
		velocity.y += gravity * delta

	move_and_slide()


func _on_area_entered(area: Area2D) -> void:
	if area.is_in_group("collectibles"):
		emit_signal("item_collected", area.name)
		area.queue_free()
	elif area.is_in_group("lap_trigger"):
		laps += 1
		emit_signal("lap_completed")