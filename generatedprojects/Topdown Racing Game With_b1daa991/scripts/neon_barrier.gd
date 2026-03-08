extends StaticBody2D

@export var neon_color: Color = Color(0.0, 1.0, 0.0)  # Green by default
@export var neon_thickness: float = 5.0
@export var neon_length: float = 50.0
@export var neon_height: float = 10.0
@export var animation_speed: float = 1.0

var _time_offset: float = 0.0

func _ready():
	add_to_group("obstacles")
	_update_polygon()

func _process(delta):
	_time_offset += delta * animation_speed
	_update_polygon()

func _update_polygon():
	var polygon = PackedVector2Array([
		Vector2(-neon_length / 2, -neon_height / 2),
		Vector2(neon_length / 2, -neon_height / 2),
		Vector2(neon_length / 2, neon_height / 2),
		Vector2(-neon_length / 2, neon_height / 2)
	])

	var color_array = PackedColorArray()
	for _i in range(polygon.size()):
		var offset = sin(_time_offset + float(_i) / float(polygon.size()) * PI * 2.0) * 0.5 + 0.5
		color_array.append(neon_color.lerp(Color(0.0, 0.0, 0.0, 0.0), offset))

	var mesh = Mesh.new()
	var array_mesh = ArrayMesh.new()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = polygon
	arrays[Mesh.ARRAY_COLOR] = color_array
	array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLE_FAN, arrays)
	mesh.add_surface(0, array_mesh.get_surface(0))

	if find_child("NeonMesh") == null:
		var mesh_instance = MeshInstance2D.new()
		mesh_instance.name = "NeonMesh"
		add_child(mesh_instance)
		mesh_instance.material = ShaderMaterial.new()
		mesh_instance.material.shader = preload("res://shaders/neon_shader.tres")
		mesh_instance.material.set_shader_parameter("neon_color", neon_color)
		mesh_instance.material.set_shader_parameter("neon_thickness", neon_thickness)
		mesh_instance.mesh = mesh
	else:
		var mesh_instance = find_child("NeonMesh") as MeshInstance2D
		mesh_instance.mesh = mesh
		mesh_instance.material.set_shader_parameter("neon_color", neon_color)
		mesh_instance.material.set_shader_parameter("neon_thickness", neon_thickness)

	# Update collision shape
	var collision_shape = find_child("CollisionShape2D") as CollisionShape2D
	if collision_shape:
		var rect_shape = collision_shape.shape as RectangleShape2D
		if rect_shape:
			rect_shape.size = Vector2(neon_length, neon_height)
		else:
			rect_shape = RectangleShape2D.new()
			rect_shape.size = Vector2(neon_length, neon_height)
			collision_shape.shape = rect_shape
	else:
		var new_collision_shape = CollisionShape2D.new()
		var rect_shape = RectangleShape2D.new()
		rect_shape.size = Vector2(neon_length, neon_height)
		new_collision_shape.shape = rect_shape
		new_collision_shape.name = "CollisionShape2D"
		add_child(new_collision_shape)