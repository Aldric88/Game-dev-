extends CharacterBody2D

@export var speed = 50.0
@export var acceleration = 200.0
@export var deceleration = 300.0
@export var rotation_speed = 50.0
@export var fire_rate = 1.0
@export var projectile_speed = 200.0
@export var health = 200
@export var score_value = 500
@export var powerup_drop_chance = 0.2

@onready var collision_shape = $CollisionShape2D
@onready var projectile_origin_left = $ProjectileOriginLeft
@onready var projectile_origin_right = $ProjectileOriginRight
@onready var projectile_origin_center = $ProjectileOriginCenter

signal enemy_destroyed(position: Vector2, score: int)
signal powerup_dropped(position: Vector2)

enum State {
	PATROL,
	CHASE,
	ATTACK
}

var state = State.PATROL
var patrol_points: Array[Vector2]
var current_patrol_point_index = 0
var player: Node2D
var time_since_last_fire = 0.0
var gravity = ProjectSettings.get_setting("physics/2d/default_gravity")

func _ready():
	add_to_group("enemies")
	patrol_points = [Vector2(-100, 0), Vector2(100, 0)] # Example patrol points
	if get_parent().has_node("Player"):
		player = get_parent().get_node("Player")
	else:
		printerr("Player node not found in parent.")

func _physics_process(delta):
	match state:
		State.PATROL:
			patrol(delta)
		State.CHASE:
			chase(delta)
		State.ATTACK:
			attack(delta)

	time_since_last_fire += delta

func patrol(delta):
	if patrol_points.size() == 0:
		return

	var target_position = patrol_points[current_patrol_point_index]
	var direction = (target_position - global_position).normalized()

	velocity = velocity.lerp(direction * speed, acceleration * delta)
	velocity = move_and_slide(velocity)

	if global_position.distance_to(target_position) < 10:
		current_patrol_point_index = (current_patrol_point_index + 1) % patrol_points.size()

	if player != null and global_position.distance_to(player.global_position) < 300:
		state = State.CHASE

func chase(delta):
	if player == null:
		state = State.PATROL
		return

	var direction = (player.global_position - global_position).normalized()

	velocity = velocity.lerp(direction * speed * 1.2, acceleration * delta)
	velocity = move_and_slide(velocity)

	if global_position.distance_to(player.global_position) < 200:
		state = State.ATTACK
	elif global_position.distance_to(player.global_position) > 400:
		state = State.PATROL

func attack(delta):
	if player == null:
		state = State.PATROL
		return

	var direction = (player.global_position - global_position).normalized()
	var target_velocity = direction * speed * 0.5
	velocity = velocity.lerp(target_velocity, acceleration * delta)
	velocity = move_and_slide(velocity)

	if time_since_last_fire > 1.0 / fire_rate:
		fire_projectiles()
		time_since_last_fire = 0.0

	if global_position.distance_to(player.global_position) > 250:
		state = State.CHASE

func fire_projectiles():
	var projectile_scene = preload("res://projectile.tscn") # Replace with your projectile scene

	var projectile1 = projectile_scene.instantiate()
	projectile1.global_position = projectile_origin_left.global_position
	var direction1 = (player.global_position - projectile1.global_position).normalized()
	projectile1.linear_velocity = direction1 * projectile_speed
	get_parent().add_child(projectile1)

	var projectile2 = projectile_scene.instantiate()
	projectile2.global_position = projectile_origin_right.global_position
	var direction2 = (player.global_position - projectile2.global_position).normalized()
	projectile2.linear_velocity = direction2 * projectile_speed
	get_parent().add_child(projectile2)

	var projectile3 = projectile_scene.instantiate()
	projectile3.global_position = projectile_origin_center.global_position
	var direction3 = (player.global_position - projectile3.global_position).normalized()
	projectile3.linear_velocity = direction3 * projectile_speed
	get_parent().add_child(projectile3)

func take_damage(damage):
	health -= damage
	if health <= 0:
		die()

func die():
	emit_signal("enemy_destroyed", global_position, score_value)
	if randf() < powerup_drop_chance:
		emit_signal("powerup_dropped", global_position)
	queue_free()