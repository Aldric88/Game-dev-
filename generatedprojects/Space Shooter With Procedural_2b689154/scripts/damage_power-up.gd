extends Area2D

signal collected(node)

@export var damage_increase: float = 2.0
@export var duration: float = 5.0
@export var hover_speed: float = 1.0
@export var hover_height: float = 5.0

var initial_position: Vector2
var time: float = 0.0

func _ready():
	add_to_group("collectibles")
	initial_position = position

func _process(delta):
	time += delta
	position.y = initial_position.y + sin(time * hover_speed) * hover_height

func _on_body_entered(body):
	if body.is_in_group("player"):
		emit_signal("collected", body)
		queue_free()