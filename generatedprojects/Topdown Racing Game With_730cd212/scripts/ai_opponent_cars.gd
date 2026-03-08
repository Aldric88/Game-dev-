extends CharacterBody2D

@export var speed = 100.0
@export var rotation_speed = 2.0
@export var drift_speed_multiplier = 0.5
@export var acceleration = 500.0
@export var braking_deceleration = 1000.0
@export var max_speed = 300.0
@export var drift_angle = 0.5
@export var path: Array[Vector2]
@export var tolerance = 10.0

var current_path_index = 0
var velocity = Vector2.ZERO
var is_drifting = false
var target_rotation = 0.0

func _ready():
	if path.size() > 0:
		target_rotation = get_angle_to_point(path[current_path_index])

func _physics_process(delta):
	if path.size() == 0:
		return
	
	var target_position = path[current_path_index]
	var direction = (target_position - global_position).normalized()
	
	# Steering
	var angle_to_target = get_angle_to_point(target_position)
	var rotation_difference = angle_to_target - rotation
	
	if abs(rotation_difference) > 0.01:
		var rotation_direction = sign(rotation_difference)
		rotation += rotation_direction * rotation_speed * delta
		rotation = wraparound(rotation, -PI, PI)
	else:
		rotation = angle_to_target
		
	# Acceleration
	velocity += transform.x * acceleration * delta
	
	# Limit speed
	velocity = velocity.limit_length(max_speed)
	
	# Move towards the target
	velocity = move_toward(velocity, transform.x * max_speed, acceleration * delta)
	
	# Check if reached the current path point
	if global_position.distance_to(target_position) < tolerance:
		current_path_index = (current_path_index + 1) % path.size()
		target_rotation = get_angle_to_point(path[current_path_index])
	
	velocity = move_and_slide(velocity)
	
	# Deceleration
	if velocity.length() > 0:
		velocity = velocity.move_toward(Vector2.ZERO, braking_deceleration * delta)