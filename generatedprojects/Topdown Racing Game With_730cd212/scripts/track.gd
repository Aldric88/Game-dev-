extends CharacterBody2D

@export var speed = 200.0
@export var rotation_speed = 3.0
@export var drift_speed_multiplier = 1.5
@export var acceleration = 200.0
@export var braking_deceleration = 500.0
@export var max_speed = 500.0
@export var drift_angle = 45.0

var velocity = Vector2.ZERO
var is_drifting = false
var current_speed = 0.0
var gravity = ProjectSettings.get_setting("physics/2d/default_gravity")

signal lap_completed()

func _physics_process(delta):
	# Steering
	var steer_direction = Input.get_axis("steer_left", "steer_right")
	rotation += steer_direction * rotation_speed * delta

	# Acceleration and Braking
	var acceleration_input = Input.get_axis("brake", "accelerate")
	if acceleration_input > 0:
		current_speed = min(current_speed + acceleration * delta, max_speed)
	elif acceleration_input < 0:
		current_speed = max(current_speed - braking_deceleration * delta, 0)
	else:
		# Natural deceleration
		current_speed = max(current_speed - braking_deceleration * 0.2 * delta, 0)

	# Drifting
	is_drifting = Input.is_action_pressed("drift")
	var drift_multiplier = 1.0
	if is_drifting:
		drift_multiplier = drift_speed_multiplier

	# Movement
	var forward_direction = Vector2(1, 0).rotated(rotation)
	velocity = forward_direction * current_speed * drift_multiplier

	move_and_slide()

func _on_lap_detector_body_entered(body):
	if body.is_in_group("player"):
		emit_signal("lap_completed")

func apply_powerup(powerup_type):
	match powerup_type:
		"speed_boost":
			max_speed *= 1.5
			await get_tree().create_timer(5.0).timeout
			max_speed /= 1.5
		"invincibility":
			# Example: Disable collision for a short duration
			set_collision_mask_value(1, false)
			await get_tree().create_timer(3.0).timeout
			set_collision_mask_value(1, true)