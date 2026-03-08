extends CharacterBody2D

@export var speed = 200.0
@export var acceleration = 500.0
@export var friction = 800.0
@export var rotation_speed = 3.0
@export var drift_angle = 45.0
@export var drift_speed_multiplier = 0.7

signal checkpoint_reached(checkpoint_id)

var velocity = Vector2.ZERO
var steering_direction = 0.0
var accelerating = false
var braking = false
var drifting = false
var current_lap = 0
var last_checkpoint = 0

func _physics_process(delta):
	steering_direction = Input.get_axis("move_left", "move_right")
	accelerating = Input.is_action_pressed("move_forward")
	braking = Input.is_action_pressed("move_backward")
	drifting = Input.is_action_pressed("drift")

	# Steering
	rotation += steering_direction * rotation_speed * delta

	# Acceleration and Braking
	if accelerating:
		velocity += transform.x * acceleration * delta
	elif braking:
		velocity -= transform.x * acceleration * delta * 0.5 # Less braking power

	# Friction
	if !accelerating and !braking:
		velocity = velocity.lerp(Vector2.ZERO, friction * delta)

	# Speed Limit
	velocity = velocity.limit_length(speed)

	# Drifting
	if drifting:
		var drift_direction = -steering_direction if steering_direction != 0 else 1
		var drift_vector = Vector2(drift_direction, 1).rotated(rotation).normalized()
		velocity = drift_vector * speed * drift_speed_multiplier
		rotation += steering_direction * rotation_speed * delta * 1.5 # Increased rotation during drift

	velocity = move_and_slide(velocity)

func _on_area_entered(area):
	if area.is_in_group("checkpoint"):
		var checkpoint_id = area.get("checkpoint_id")
		if checkpoint_id == last_checkpoint + 1 or (checkpoint_id == 0 and last_checkpoint == get_node("/root/Game").get("total_checkpoints") - 1):
			last_checkpoint = checkpoint_id
			emit_signal("checkpoint_reached", checkpoint_id)
			if checkpoint_id == 0:
				current_lap += 1
				print("Lap: ", current_lap)