extends CharacterBody2D

@export var speed_max: float = 200.0
@export var acceleration: float = 500.0
@export var deceleration: float = 700.0
@export var rotation_speed: float = 200.0
@export var health_max: int = 100
@export var bullet_speed: float = 400.0
@export var fire_rate: float = 0.2 # Seconds between shots
@export var weapon_offset: Vector2 = Vector2(20, 0)

signal health_changed(new_health: int)
signal died

var health: int = health_max
var velocity: Vector2 = Vector2.ZERO
var rotation_direction: float = 0.0
var can_shoot: bool = true
var time_since_last_shot: float = 0.0
var current_weapon: int = 0 # Index of weapon in weapon_list
var weapon_list: Array[String] = ["Laser", "Missile"] # Example weapon names

@onready var collision_shape: CollisionShape2D = $CollisionShape2D
@onready var sprite: Sprite2D = $Sprite2D
@onready var weapon_spawn_point: Node2D = $WeaponSpawnPoint

func _ready():
	add_to_group("player")

func _physics_process(delta):
	# Movement
	var move_axis = Input.get_axis("move_left", "move_right")
	var thrust_axis = Input.get_axis("move_down", "move_up") # Inverted for space
	
	if thrust_axis != 0:
		velocity += Vector2(0, thrust_axis).rotated(rotation) * acceleration * delta
	else:
		# Deceleration
		if velocity.length() > 0:
			var deceleration_vector = -velocity.normalized() * deceleration * delta
			if velocity.length() > deceleration_vector.length():
				velocity += deceleration_vector
			else:
				velocity = Vector2.ZERO

	velocity = velocity.limit_length(speed_max)
	
	# Rotation
	rotation_direction = Input.get_axis("rotate_left", "rotate_right")
	rotation += rotation_direction * rotation_speed * delta
	
	velocity = move_and_slide(velocity)

	# Shooting
	if Input.is_action_pressed("shoot") and can_shoot:
		_shoot()
	
	if not can_shoot:
		time_since_last_shot += delta
		if time_since_last_shot >= fire_rate:
			can_shoot = true
			time_since_last_shot = 0.0
			
	# Weapon Switching
	if Input.is_action_just_pressed("switch_weapon"):
		current_weapon = (current_weapon + 1) % weapon_list.size()
		print("Switched to weapon: ", weapon_list[current_weapon])

func _shoot():
	can_shoot = false
	var bullet = Sprite2D.new() # Replace with your bullet scene
	bullet.texture = preload("res://icon.svg") # Replace with your bullet texture
	get_parent().add_child(bullet)
	bullet.global_position = weapon_spawn_point.global_position
	bullet.global_rotation = rotation
	var bullet_direction = Vector2(1, 0).rotated(rotation)
	bullet.velocity = bullet_direction * bullet_speed
	bullet.add_to_group("player_bullets")
	
	var bullet_collision = CollisionShape2D.new()
	var bullet_shape = CircleShape2D.new()
	bullet_shape.radius = 5
	bullet_collision.shape = bullet_shape
	bullet.add_child(bullet_collision)
	
	bullet.script = preload("res://bullet.gd") # Replace with your bullet script
	bullet.lifetime = 2.0 # Example lifetime
	
	print("Firing ", weapon_list[current_weapon])

func take_damage(damage: int):
	health -= damage
	health = max(health, 0)
	emit_signal("health_changed", health)
	
	if health <= 0:
		die()

func die():
	# Spawn explosion animation
	# Queue free
	queue_free()
	emit_signal("died")
	print("Player died!")