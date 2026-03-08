extends Node2D

@export var animation_speed : float = 1.0
@export var color1 : Color = Color(1.0, 0.0, 0.0)
@export var color2 : Color = Color(0.0, 0.0, 1.0)

@onready var sprite : Sprite2D = $Sprite2D

var time : float = 0.0

func _ready():
	set_process(true)

func _process(delta):
	time += delta * animation_speed
	var color = color1.lerp(color2, abs(sin(time)))
	sprite.modulate = color