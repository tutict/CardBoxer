extends RefCounted
## One scalar per hand drives the same progressive geometry and contact socket.
const DEFAULT := .75
const TARGET_NAMES := ["grip_half_f","grip_f","grip_half_b","grip_b"]

static func valid_grip(value: Variant) -> bool:
	if not value is Array or value.size()!=2: return false
	for number: Variant in value:
		if not (number is float or number is int) or not is_finite(float(number)) or float(number)<0.0 or float(number)>1.0: return false
	return true

static func grip(pose: Dictionary) -> Array:
	var value: Variant = pose.get("hand_grip",[DEFAULT,DEFAULT])
	return value.duplicate() if valid_grip(value) else []

## Returned components are Basis, half and fully closed coefficients.
static func weights(amount: float) -> Vector3:
	var g := clampf(amount,0.0,1.0)
	if g<=.5: return Vector3(1.0-2.0*g,2.0*g,0.0)
	return Vector3(0.0,2.0*(1.0-g),2.0*g-1.0)

static func valid_profile(profile: Dictionary) -> bool:
	var sockets: Variant = profile.get("hand_sockets")
	if not sockets is Dictionary: return false
	for hand: String in ["front","rear"]:
		if not sockets.get(hand) is Dictionary: return false
		for state: String in ["open","half","closed"]:
			var point: Variant = sockets[hand].get(state)
			if not point is Array or point.size()!=3: return false
			for number: Variant in point:
				if not (number is float or number is int) or not is_finite(float(number)): return false
	return true

static func socket(profile: Dictionary, front: bool, amount: float) -> Vector3:
	var states: Dictionary = profile.hand_sockets["front" if front else "rear"]
	var mix := weights(amount)
	var result := Vector3.ZERO
	var names := ["open","half","closed"]
	for index in range(3):
		var point: Array = states[names[index]]
		result += Vector3(float(point[0]),float(point[1]),float(point[2]))*mix[index]
	return result
