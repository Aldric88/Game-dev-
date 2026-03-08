extends Area2D

signal race_finished

@export var checkered_size: Vector2 = Vector2(32, 32)
@export var checkered_color_1: Color = Color.WHITE
@export var checkered_color_2: Color = Color.BLACK

@onready var sprite: Sprite2D = Sprite2D.new()

func _ready():
	add_to_group("collectibles")
	
	# Create checkered pattern texture
	var image = Image.create(int(checkered_size.x), int(checkered_size.y), false, Image.FORMAT_RGBA8)
	for x in range(int(checkered_size.x)):
		for y in range(int(checkered_size.y)):
			if (x + y) % 2 == 0:
				image.set_pixel(x, y, checkered_color_1)
			else:
				image.set_pixel(x, y, checkered_color_2)
	var texture = ImageTexture.create_from_image(image)
	sprite.texture = texture
	sprite.centered = false
	add_child(sprite)
	
	# Create a larger CollisionShape2D to cover the visual area
	var collision_shape = CollisionShape2D.new()
	var rect_shape = RectangleShape2D.new()
	rect_shape.size = checkered_size * 4 # Adjust size as needed to cover the visual area
	collision_shape.shape = rect_shape
	add_child(collision_shape)


func _on_body_entered(body: Node2D):
	if body.is_in_group("player"):
		emit_signal("race_finished")
		queue_free()