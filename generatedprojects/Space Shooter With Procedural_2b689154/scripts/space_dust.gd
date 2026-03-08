extends Node2D

@export var speed: float = 10.0
@export var direction: Vector2 = Vector2(-1, 0)
@export var color: Color = Color.WHITE
@export var size: float = 2.0

var _velocity: Vector2 = Vector2.ZERO

func _ready():
	_velocity = direction.normalized() * speed
	var sprite = Sprite2D.new()
	sprite.texture = CircleTexture.new()
	sprite.scale = Vector2(size, size)
	sprite.modulate = color
	add_child(sprite)

func _process(delta):
	position += _velocity * delta

	# Wrap around screen
	var viewport_size = get_viewport_rect().size
	if position.x < 0:
		position.x = viewport_size.x
	elif position.x > viewport_size.x:
		position.x = 0
	if position.y < 0:
		position.y = viewport_size.y
	elif position.y > viewport_size.y:
		position.y = 0