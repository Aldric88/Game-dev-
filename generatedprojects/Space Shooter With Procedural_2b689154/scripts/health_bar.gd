extends TextureProgressBar

@export var max_health : int = 100
var current_health : int = 100

@onready var player = get_tree().get_first_node_in_group("player")

func _ready():
	max_value = max_health
	value = current_health
	if player:
		player.health_changed.connect(_on_player_health_changed)

func _on_player_health_changed(new_health : int):
	current_health = new_health
	value = current_health

func take_damage(damage : int):
	current_health -= damage
	current_health = clamp(current_health, 0, max_health)
	value = current_health
	if player:
		player.health_changed.emit(current_health)