extends Control

signal weapon_icon_pressed(weapon_index: int)

@export var icon_size: Vector2 = Vector2(64, 64)
@export var icon_spacing: float = 10.0
@export var highlight_color: Color = Color("yellow")

@onready var hbox_container: HBoxContainer = HBoxContainer.new()

var weapon_icons: Array[TextureRect] = []
var weapon_textures: Array[Texture2D] = []
var current_weapon_index: int = 0

func _ready():
	add_child(hbox_container)
	hbox_container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	hbox_container.alignment = BoxContainer.ALIGN_CENTER
	hbox_container.add_theme_constant_override("separation", icon_spacing)

func set_weapon_textures(textures: Array[Texture2D]):
	weapon_textures = textures
	_update_icons()

func set_current_weapon(index: int):
	current_weapon_index = index
	_update_icons()

func _update_icons():
	# Clear existing icons
	for icon in weapon_icons:
		icon.queue_free()
	weapon_icons.clear()

	# Create new icons
	for i in range(weapon_textures.size()):
		var icon: TextureRect = TextureRect.new()
		icon.texture = weapon_textures[i]
		icon.set_size(icon_size)
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.mouse_filter = Control.MOUSE_FILTER_STOP

		var button: Button = Button.new()
		button.add_child(icon)
		button.flat = true
		button.connect("pressed", _on_weapon_button_pressed.bind(i))
		button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		button.size_flags_vertical = Control.SIZE_SHRINK_CENTER

		hbox_container.add_child(button)
		weapon_icons.append(icon)

	_highlight_current_weapon()

func _highlight_current_weapon():
	for i in range(weapon_icons.size()):
		if i == current_weapon_index:
			weapon_icons[i].modulate = highlight_color
		else:
			weapon_icons[i].modulate = Color.WHITE

func _on_weapon_button_pressed(weapon_index: int):
	emit_signal("weapon_icon_pressed", weapon_index)