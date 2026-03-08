extends CharacterBody2D

@export var acceleration: float = 2000.0
@export var max_speed: float = 400.0
@export var rotation_speed: float = 3.0
@export var drift_rotation_multiplier: float = 0.5
@export var drift_acceleration_multiplier: float = 0.7
@export var drift_deceleration_multiplier: float = 0.95
@export var braking_force: float = 3000.0
@export var friction: float = 100.0
@export var drift_friction: float = 5.0
@export var boost_speed: float = 800.0
@export var boost_duration: float = 2.0

@onready var sprite: Sprite2D = $Sprite2D

var speed: float = 0.0
var steering: float = 0.0
var is_drifting: bool = false
var boost_timer: float = 0.0
var is_boosting: bool = false
var velocity: Vector2 = Vector2.ZERO

signal boost_activated

func _ready():
	add_to_group("player")

func _physics_process(delta: float):
	get_input(delta)
	apply_movement(delta)
	apply_drift(delta)
	apply_boost(delta)
	move_and_slide()

func get_input(delta: float):
	steering = Input.get_axis("steer_left", "steer_right")
	is_drifting = Input.is_action_pressed("drift")
	if Input.is_action_just_pressed("boost") and !is_boosting:
		activate_boost()

	if Input.is_action_pressed("brake"):
		speed = max(0.0, speed - braking_force * delta)
	else:
		var acceleration_direction = Input.get_axis("accelerate", "decelerate")
		if acceleration_direction != 0:
			speed += acceleration_direction * acceleration * delta
			speed = clamp(speed, -max_speed * 0.5, max_speed)
		else:
			# Natural deceleration
			if speed > 0:
				speed = max(0.0, speed - friction * delta)
			elif speed < 0:
				speed = min(0.0, speed + friction * delta)

func apply_movement(delta: float):
	var rotation_amount = steering * rotation_speed * delta
	if is_drifting:
		rotation_amount *= drift_rotation_multiplier
	
	rotation += rotation_amount

	var forward_direction = Vector2(0, -1).rotated(rotation)
	velocity = forward_direction * speed

func apply_drift(delta: float):
	if is_drifting:
		speed *= drift_deceleration_multiplier
		apply_central_impulse(-velocity.normalized() * friction * drift_friction * delta)
		
		# Visual feedback for drifting (optional)
		# sprite.modulate = Color("red")
	else:
		# sprite.modulate = Color("white")
		pass

func apply_boost(delta: float):
	if is_boosting:
		boost_timer -= delta
		speed = max(speed, boost_speed)
		if boost_timer <= 0:
			is_boosting = false

func activate_boost():
	if !is_boosting:
		is_boosting = true
		boost_timer = boost_duration
		emit_signal("boost_activated")

func _on_area_entered(area: Area2D):
	if area.is_in_group("collectibles"):
		area.collect()