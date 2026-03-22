extends Area2D

const SPEED := 500.0
const DAMAGE := 10.0
const LIFETIME := 3.0

var direction := Vector2.RIGHT
var _timer := 0.0

func _ready() -> void:
	add_to_group("projectiles")
	body_entered.connect(_on_body_entered)

func _physics_process(delta: float) -> void:
	position += direction * SPEED * delta
	_timer += delta
	if _timer >= LIFETIME:
		queue_free()

func _on_body_entered(body: Node2D) -> void:
	if body.is_in_group("enemies") and body.has_method("take_damage"):
		body.take_damage(DAMAGE)
	queue_free()
