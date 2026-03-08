extends Area2D

signal collected(amount)

@export var health_amount: int = 25
@export var hover_speed: float = 1.0
@export var hover_height: float = 5.0

var initial_position: Vector2
var time_offset: float = randf_range(0, PI * 2)

func _ready():
	add_to_group("collectibles")
	initial_position = position

func _process(delta):
	var hover_offset = Vector2(0, sin(Time.get_ticks_msec() / 1000.0 * hover_speed + time_offset) * hover_height)
	position = initial_position + hover_offset

func _on_body_entered(body):
	if body.is_in_group("player"):
		emit_signal("collected", health_amount)
		queue_free()