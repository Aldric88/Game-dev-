extends Control

@export var target_node: Node2D
@export var speed_multiplier: float = 1.0
@export var speed_unit: String = " km/h"

@onready var speed_label: Label = $SpeedLabel

func _physics_process(delta: float) -> void:
	if target_node is RigidBody2D:
		var speed: float = target_node.linear_velocity.length() * speed_multiplier
		speed_label.text = str(int(speed)) + speed_unit
	elif target_node is CharacterBody2D:
		var speed: float = target_node.velocity.length() * speed_multiplier
		speed_label.text = str(int(speed)) + speed_unit
	else:
		speed_label.text = "N/A"