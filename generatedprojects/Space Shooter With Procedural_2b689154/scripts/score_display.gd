extends Label

@export var score: int = 0
@export var score_multiplier: float = 1.0

signal score_changed(new_score: int)

func _ready():
	text = "Score: %d" % score
	emit_signal("score_changed", score)

func add_score(points: int):
	score += int(points * score_multiplier)
	text = "Score: %d" % score
	emit_signal("score_changed", score)

func set_score_multiplier(multiplier: float):
	score_multiplier = multiplier

func get_score() -> int:
	return score

func get_score_multiplier() -> float:
	return score_multiplier