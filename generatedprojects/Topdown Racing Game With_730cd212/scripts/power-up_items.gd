extends Area2D

signal collected(item_type)

@export var item_type: String = "speed_boost"
@export var respawn_time: float = 5.0
var is_collected: bool = false
var original_position: Vector2

func _ready():
	original_position = position

func _on_body_entered(body):
	if is_collected:
		return

	if body.is_in_group("player"):
		emit_signal("collected", item_type)
		is_collected = true
		hide()
		$CollisionShape2D.disabled = true
		$Timer.start(respawn_time)

func _on_timer_timeout():
	is_collected = false
	position = original_position
	show()
	$CollisionShape2D.disabled = false