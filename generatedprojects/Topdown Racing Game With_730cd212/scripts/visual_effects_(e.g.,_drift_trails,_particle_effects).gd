extends Node2D

@export var drift_trail_scene: PackedScene
@export var particle_effect_scene: PackedScene

func create_drift_trail(position: Vector2, rotation: float):
	var drift_trail = drift_trail_scene.instantiate()
	add_child(drift_trail)
	drift_trail.global_position = position
	drift_trail.rotation = rotation

func create_particle_effect(position: Vector2, color: Color):
	var particle_effect = particle_effect_scene.instantiate()
	add_child(particle_effect)
	particle_effect.global_position = position
	particle_effect.color = color