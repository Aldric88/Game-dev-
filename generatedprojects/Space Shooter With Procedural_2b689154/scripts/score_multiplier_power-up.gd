extends Area2D

signal collected(duration, multiplier)

@export var duration : float = 5.0
@export var multiplier : float = 2.0
@export var hover_speed : float = 1.0
@export var hover_height : float = 5.0

var initial_y : float
var time : float = 0.0

func _ready():
	add_to_group("collectibles")
	initial_y = position.y

func _process(delta):
	time += delta
	position.y = initial_y + sin(time * hover_speed) * hover_height

func _on_body_entered(body):
	if body.is_in_group("player"):
		emit_signal("collected", duration, multiplier)
		queue_free()