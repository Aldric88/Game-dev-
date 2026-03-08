extends CharacterBody2D

@export var max_speed: float = 200.0
@export var acceleration: float = 500.0
@export var deceleration: float = 700.0
@export var steering_speed: float = 3.0
@export var drift_angle_threshold: float = 0.5 # Radians
@export var drift_multiplier: float = 0.7
@export var collision_avoidance_distance: float = 50.0
@export var collision_avoidance_strength: float = 0.5
@export var boost_speed: float = 400.0
@export var boost_duration: float = 2.0

var current_speed: float = 0.0
var steering_direction: float = 0.0
var is_drifting: bool = false
var boost_timer: float = 0.0
var target_position: Vector2
var path: PackedVector2Array
var path_index: int = 0
var player: CharacterBody2D
var is_drafting: bool = false
var drafting_timer: float = 0.0
var drafting_speed_multiplier: float = 1.1

signal boost_activated

func _ready():
	add_to_group("enemies")
	target_position = global_position
	path = []
	player = null # Initialize player to null
	find_player()
	
func find_player():
	var players = get_tree().get_nodes_in_group("player")
	if !players.is_empty():
		player = players[0]

func _physics_process(delta):
	if player == null:
		find_player()
		return
		
	if boost_timer > 0:
		boost_timer -= delta
	
	if drafting_timer > 0:
		drafting_timer -= delta
		if drafting_timer <= 0:
			is_drafting = false

	# Pathfinding
	if path.is_empty() or global_position.distance_to(target_position) < 20:
		update_path()

	if !path.is_empty():
		target_position = path[path_index]
		var direction = (target_position - global_position).normalized()

		# Collision Avoidance
		var collision_avoidance_vector = get_collision_avoidance_vector()
		direction += collision_avoidance_vector * collision_avoidance_strength

		# Steering
		steering_direction = get_steering_direction(direction)

		# Drifting
		if abs(steering_direction) > drift_angle_threshold and current_speed > max_speed * 0.5:
			is_drifting = true
		else:
			is_drifting = false

		# Acceleration/Deceleration
		var target_speed = max_speed
		if boost_timer > 0:
			target_speed = boost_speed
		elif is_drafting:
			target_speed *= drafting_speed_multiplier
			
		if direction.dot(transform.x) > 0:  # Moving forward
			current_speed = min(current_speed + acceleration * delta, target_speed)
		else:
			current_speed = max(current_speed - deceleration * delta, 0.0)

	else:
		current_speed = max(current_speed - deceleration * delta, 0.0)

	# Apply movement
	var forward_direction = transform.x
	if is_drifting:
		forward_direction = forward_direction.rotated(steering_direction * drift_multiplier)

	velocity = forward_direction * current_speed
	rotation += steering_direction * steering_speed * delta * (current_speed / max_speed)

	move_and_slide()

func get_steering_direction(direction: Vector2) -> float:
	return sign(transform.x.rotated(PI / 2).dot(direction))

func get_collision_avoidance_vector() -> Vector2:
	var space_state = get_world_2d().direct_space_state
	var query = PhysicsRayQueryParameters2D.new()
	query.from = global_position
	query.exclude = [self]
	query.collision_mask = 1 # Assuming walls are on layer 1
	
	var avoidance_vector = Vector2.ZERO
	
	# Check left
	query.to = global_position + transform.x.rotated(PI / 4) * collision_avoidance_distance
	var result_left = space_state.intersect_ray(query)
	if result_left:
		avoidance_vector += transform.x.rotated(-PI / 2) * (1 - (global_position.distance_to(result_left.position) / collision_avoidance_distance))
		
	# Check right
	query.to = global_position + transform.x.rotated(-PI / 4) * collision_avoidance_distance
	var result_right = space_state.intersect_ray(query)
	if result_right:
		avoidance_vector += transform.x.rotated(PI / 2) * (1 - (global_position.distance_to(result_right.position) / collision_avoidance_distance))
		
	return avoidance_vector.normalized()

func update_path():
	if player == null:
		return
	var nav = get_node("/root/Main/Navigation2D") # Replace with your Navigation2D node path
	if nav:
		path = nav.get_path(global_position, player.global_position)
		path_index = 0
		if !path.is_empty():
			target_position = path[path_index]

func _on_area_2d_area_entered(area: Area2D):
	if area.is_in_group("collectibles"):
		if area.has_method("apply_effect"):
			area.apply_effect(self)
		area.queue_free()

func activate_boost():
	boost_timer = boost_duration
	emit_signal("boost_activated")
	
func start_drafting():
	is_drafting = true
	drafting_timer = 3.0