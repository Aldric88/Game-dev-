extends CharacterBody2D

@export var max_health: int = 200
@export var move_speed: float = 50.0
@export var acceleration: float = 200.0
@export var deceleration: float = 300.0
@export var patrol_distance: float = 100.0
@export var chase_distance: float = 300.0
@export var attack_range: float = 150.0
@export var fire_rate: float = 0.5 # Attacks per second
@export var bullet_speed: float = 400.0

@onready var initial_position: Vector2 = position
@onready var health_bar: ProgressBar = $HealthBar
@onready var attack_timer: Timer = $AttackTimer

signal boss_defeated
signal weapon_part_dropped(part_name: String)

enum State {
	PATROL,
	CHASE,
	ATTACK,
	PHASE_TRANSITION,
	DEAD
}

var current_state: State = State.PATROL
var current_health: int
var player: Node2D
var patrol_direction: int = 1
var last_attack_time: float = 0.0
var phase: int = 1
var phase_health_threshold: int

func _ready():
	add_to_group("enemies")
	current_health = max_health
	health_bar.max_value = max_health
	health_bar.value = current_health
	player = get_tree().get_first_node_in_group("player")
	attack_timer.wait_time = 1.0 / fire_rate
	attack_timer.timeout.connect(_on_attack_timer_timeout)

	phase_health_threshold = max_health / 3  # Example: Transition every 1/3 health

func _physics_process(delta):
	if current_state != State.DEAD:
		match current_state:
			State.PATROL:
				patrol(delta)
			State.CHASE:
				chase(delta)
			State.ATTACK:
				attack(delta)
			State.PHASE_TRANSITION:
				phase_transition(delta)

		move_and_slide()

func patrol(delta):
	var target_position = initial_position + Vector2(patrol_distance * patrol_direction, 0)
	var direction = (target_position - position).normalized()
	velocity = velocity.lerp(direction * move_speed, acceleration * delta)

	if position.distance_to(target_position) < 10:
		patrol_direction *= -1

	if player and position.distance_to(player.position) < chase_distance:
		current_state = State.CHASE

func chase(delta):
	if player:
		var direction = (player.position - position).normalized()
		velocity = velocity.lerp(direction * move_speed, acceleration * delta)

		if position.distance_to(player.position) < attack_range:
			current_state = State.ATTACK
	else:
		current_state = State.PATROL

	if position.distance_to(initial_position) > chase_distance * 1.5:
		current_state = State.PATROL

func attack(delta):
	if player:
		var direction = (player.position - position).normalized()
		velocity = velocity.lerp(Vector2.ZERO, deceleration * delta)

		# Attack handled by timer
	else:
		current_state = State.PATROL

	if position.distance_to(player.position) > attack_range * 1.2:
		current_state = State.CHASE

func _on_attack_timer_timeout():
	if current_state == State.ATTACK and player:
		# Implement different attack patterns based on phase
		match phase:
			1:
				fire_laser()
			2:
				fire_missiles()
			3:
				fire_spread_shot()

func fire_laser():
	var bullet = preload("res://bullet.tscn").instantiate() # Replace with your bullet scene
	bullet.position = position
	bullet.direction = (player.position - position).normalized()
	bullet.speed = bullet_speed
	get_parent().add_child(bullet)

func fire_missiles():
	for i in range(-1, 2):
		var bullet = preload("res://missile.tscn").instantiate() # Replace with your missile scene
		bullet.position = position
		bullet.direction = (player.position - position + Vector2(i * 20, 0)).normalized()
		bullet.speed = bullet_speed * 0.8
		get_parent().add_child(bullet)

func fire_spread_shot():
	for i in range(-2, 3):
		var bullet = preload("res://spread_bullet.tscn").instantiate() # Replace with your spread bullet scene
		bullet.position = position
		bullet.direction = (player.position - position + Vector2(i * 10, 0)).normalized()
		bullet.speed = bullet_speed * 0.6
		get_parent().add_child(bullet)

func take_damage(damage: int):
	current_health -= damage
	health_bar.value = current_health

	if current_health <= 0:
		die()
	elif current_health <= phase_health_threshold * (phase - 1) and current_state != State.PHASE_TRANSITION and phase < 3:
		current_state = State.PHASE_TRANSITION
		phase += 1
		phase_transition_start()

func phase_transition(delta):
	# Implement phase transition animation or behavior
	pass

func phase_transition_start():
	# Called at the start of the phase transition
	attack_timer.stop()
	velocity = Vector2.ZERO
	# Add transition animation logic here
	await get_tree().create_timer(3.0).timeout # Example transition time
	attack_timer.start()
	current_state = State.PATROL # Or CHASE, depending on design

func die():
	current_state = State.DEAD
	attack_timer.stop()
	velocity = Vector2.ZERO
	emit_signal("boss_defeated")
	drop_weapon_part()
	queue_free()

func drop_weapon_part():
	var parts = ["laser_upgrade", "missile_launcher", "spread_shot_module"]
	var random_part = parts[randi_range(0, parts.size() - 1)]
	emit_signal("weapon_part_dropped", random_part)