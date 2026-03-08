extends Control

@export var font_size: int = 32
@export var lap_count: int = 1
@export var total_laps: int = 3

signal lap_completed

@onready var label: Label = Label.new()

func _ready():
	# Setup Label
	label.name = "LapCounterLabel"
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.size_flags_horizontal = SIZE_FILL
	label.size_flags_vertical = SIZE_FILL
	label.theme_override_font_sizes.default_font_size = font_size
	add_child(label)

	# Initial display
	update_display()

func _process(_delta):
	pass # No continuous update needed

func increment_lap():
	lap_count += 1
	update_display()
	if lap_count > total_laps:
		lap_count = total_laps
		emit_signal("lap_completed")

func reset_lap_count():
	lap_count = 1
	update_display()

func update_display():
	label.text = "Lap: " + str(lap_count) + "/" + str(total_laps)