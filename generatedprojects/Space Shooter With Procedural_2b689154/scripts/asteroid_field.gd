extends RigidBody2D

@export var speed: float = 50.0
@export var damage: float = 25.0
@export var health: float = 50.0
@export var score_value: int = 10
@export var rotation_speed: float = 10.0

signal asteroid_destroyed(position: Vector2, score: int)

var direction: Vector2 = Vector2(-1, 0) # Move left by default
var initial_scale: float

func _ready():
	initial_scale = scale.x
	set_collision_layer_value(3, true) # Set to "Asteroids" layer
	set_collision_mask_value(1, true) # Collide with "Player"
	set_collision_mask_value(2, true) # Collide with "Projectiles"

func _physics_process(delta):
	linear_velocity = direction * speed
	rotation += rotation_speed * delta

func _on_body_entered(body):
	if body.is_in_group("player"):
		body.take_damage(damage)

func take_damage(amount: float):
	health -= amount
	if health <= 0:
		die()

func die():
	asteroid_destroyed.emit(global_position, score_value)
	queue_free()

func set_direction(new_direction: Vector2):
	direction = new_direction.normalized()

func set_scale_variance(variance: float):
	var new_scale = initial_scale + randf_range(-variance, variance)
	scale = Vector2(new_scale, new_scale)

func _on_visibility_notifier_screen_exited():
	queue_free()