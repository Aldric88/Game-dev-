extends Area2D

signal collected

var _hover_time := 0.0

func _ready() -> void:
	body_entered.connect(_on_body_entered)
	add_to_group("collectibles")

func _process(delta: float) -> void:
	_hover_time += delta
	position.y += sin(_hover_time * 3.0) * 0.3

func _on_body_entered(body: Node2D) -> void:
	if body.is_in_group("player"):
		collected.emit()
		queue_free()
