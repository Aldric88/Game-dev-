extends CharacterBody2D

@export var speed: float = 50.0
@export var acceleration: float = 200.0
@export var deceleration: float = 400.0
@export var fire_rate: float = 1.0
@export var projectile_speed: float = 200.0
@export var health: int = 3
@export var score_value: int = 100
@export var difficulty_scale: float = 1.0

signal enemy_destroyed(score: int)

@onready var collision_shape: CollisionShape2D = $CollisionShape2D
@onready var sprite: Sprite2D = $Sprite2D
@onready var projectile_spawn_point: Marker2D = $ProjectileSpawnPoint

var velocity: Vector2 = Vector2.ZERO
var target_position: Vector2 = Vector2.ZERO
var time_since_last_shot: float = 0.0
var patrol_points: Array[Vector2]
var current_patrol_point_index: int = 0
var player: Node2D

enum State {
	PATROL,
	CHASE
}

var current_state: State = State.PATROL

func _ready():
	add_to_group("enemies")
	randomize_stats()
	patrol_points = create_patrol_pattern()
	if get_tree().has_group("player"):
		player = get_tree().get_nodes_in_group("player")[0]
	else:
		current_state = State.PATROL

func _process(delta):
	time_since_last_shot += delta

	match current_state:
		State.PATROL:
			patrol(delta)
			if player != null and is_player_in_range():
				current_state = State.CHASE
		State.CHASE:
			chase(delta)
			if player == null or not is_player_in_range():
				current_state = State.PATROL

	if time_since_last_shot >= fire_rate:
		shoot()
		time_since_last_shot = 0.0

func _physics_process(delta):
	velocity = velocity.limit_length(speed)
	move_and_slide()

func patrol(delta):
	if patrol_points.size() == 0:
		return
	target_position = patrol_points[current_patrol_point_index]

	var direction: Vector2 = (target_position - global_position).normalized()

	if global_position.distance_to(target_position) < 5:
		current_patrol_point_index = (current_patrol_point_index + 1) % patrol_points.size()

	velocity = velocity.move_toward(direction * speed, acceleration * delta)

func chase(delta):
	if player == null:
		return
	var direction: Vector2 = (player.global_position - global_position).normalized()
	velocity = velocity.move_toward(direction * speed, acceleration * delta)

func shoot():
	if player == null:
		return

	var projectile = Projectile.new()
	projectile.global_position = projectile_spawn_point.global_position
	var direction = (player.global_position - projectile_spawn_point.global_position).normalized()
	projectile.set_direction(direction)
	projectile.speed = projectile_speed
	get_parent().add_child(projectile)

func take_damage(damage: int):
	health -= damage
	if health <= 0:
		die()

func die():
	emit_signal("enemy_destroyed", score_value)
	queue_free()

func randomize_stats():
	speed *= randf_range(0.8, 1.2) * difficulty_scale
	fire_rate *= randf_range(0.7, 1.3) / difficulty_scale
	health = int(health * randf_range(0.9, 1.1) * difficulty_scale)
	score_value = int(score_value * difficulty_scale)

func create_patrol_pattern() -> Array[Vector2]:
	var pattern: Array[Vector2]
	var pattern_size: int = 4
	var radius: float = 50.0
	for i in range(pattern_size):
		var angle: float = i * (2 * PI / pattern_size)
		var point: Vector2 = Vector2(cos(angle) * radius, sin(angle) * radius)
		pattern.append(global_position + point)
	return pattern

func is_player_in_range() -> bool:
	if player == null:
		return false
	var distance_to_player: float = global_position.distance_to(player.global_position)
	return distance_to_player < 200 * difficulty_scale

class Projectile extends Area2D:
	@export var speed: float = 200.0
	var direction: Vector2 = Vector2.RIGHT

	func _ready():
		add_to_group("enemy_projectiles")

	func _physics_process(delta):
		global_position += direction * speed * delta

		if global_position.x < -100 or global_position.x > 1000 or global_position.y < -100 or global_position.y > 700:
			queue_free()

	func set_direction(new_direction: Vector2):
		direction = new_direction

	func _on_body_entered(body):
		if body.is_in_group("player"):
			body.take_damage(1)
			queue_free()