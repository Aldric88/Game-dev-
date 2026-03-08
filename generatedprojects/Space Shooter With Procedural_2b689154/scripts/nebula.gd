extends Node2D

@export var drift_speed: float = 10.0
@export var drift_direction: Vector2 = Vector2(1, 0)

@onready var sprite: Sprite2D = $Sprite2D

func _ready():
	drift_direction = drift_direction.normalized()
	# Add to the "environment" group for potential global effects or management
	add_to_group("environment")

func _process(delta):
	position += drift_direction * drift_speed * delta

	# Optional: Add some subtle color shifting for visual interest
	var color_shift = sin(Time.get_ticks_msec() / 1000.0) * 0.05
	sprite.modulate = Color(1 + color_shift, 1 - color_shift, 1 + color_shift, 1)