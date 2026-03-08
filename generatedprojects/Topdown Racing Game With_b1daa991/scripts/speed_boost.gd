extends Area2D

signal collected

@export var boost_amount: float = 500.0
@export var duration: float = 2.0
@export var hover_speed: float = 1.0
@export var hover_height: float = 5.0
@export var glow_intensity: float = 2.0

@onready var initial_position: Vector2 = position
@onready var sprite: Sprite2D = $Sprite2D
@onready var collision_shape: CollisionShape2D = $CollisionShape2D

var time: float = 0.0

func _ready():
	add_to_group("collectibles")

func _process(delta):
	time += delta
	var hover_offset: float = sin(time * hover_speed) * hover_height
	position = initial_position + Vector2(0, hover_offset)
	sprite.modulate = Color(1, 1, 1, 1 + sin(time * 3) * glow_intensity * 0.1)

func _on_body_entered(body):
	if body.is_in_group("player"):
		emit_signal("collected", boost_amount, duration)
		queue_free()