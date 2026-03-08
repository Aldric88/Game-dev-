extends Node2D

@onready var speedometer_label: Label = $SpeedometerLabel
@onready var lap_counter_label: Label = $LapCounterLabel
@onready var position_indicator_label: Label = $PositionIndicatorLabel

var current_speed: float = 0.0
var current_lap: int = 1
var current_position: int = 1

signal lap_completed(lap_number: int)

func _ready():
	update_speedometer()
	update_lap_counter()
	update_position_indicator()

func update_speed(speed: float):
	current_speed = speed
	update_speedometer()

func update_lap():
	current_lap += 1
	update_lap_counter()
	emit_signal("lap_completed", current_lap)

func update_position(position: int):
	current_position = position
	update_position_indicator()

func update_speedometer():
	if is_instance_valid(speedometer_label):
		speedometer_label.text = "Speed: " + str(int(current_speed)) + " km/h"

func update_lap_counter():
	if is_instance_valid(lap_counter_label):
		lap_counter_label.text = "Lap: " + str(current_lap)

func update_position_indicator():
	if is_instance_valid(position_indicator_label):
		position_indicator_label.text = "Position: " + str(current_position)