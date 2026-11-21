extends SceneTree
## Verifies real imported morph arrays and sockets after skinning, not a fixture.
const Layer = preload("res://scripts/fighter_3d_layer.gd")
const Motion = preload("res://scripts/native_motion.gd")
const Hands = preload("res://scripts/hand_shape.gd")
var failures: Array[String] = []
var total := 0
var max_socket_error := 0.0

func expect(ok: bool,label: String) -> void:
	total+=1
	if not ok: failures.append(label)

func closest(point: Vector3,a: Vector3,b: Vector3,c: Vector3) -> Vector3:
	var u := b-a
	var v := c-a
	var n := u.cross(v)
	if n.length_squared()>1e-16:
		var projected := point-n*((point-a).dot(n)/n.length_squared())
		var q := projected-a
		var den := u.dot(u)*v.dot(v)-u.dot(v)*u.dot(v)
		if den>1e-16:
			var s := (v.dot(v)*q.dot(u)-u.dot(v)*q.dot(v))/den
			var t := (u.dot(u)*q.dot(v)-u.dot(v)*q.dot(u))/den
			if s>=0.0 and t>=0.0 and s+t<=1.0: return projected
	var result := Geometry3D.get_closest_point_to_segment(point,a,b)
	for segment: Array in [[b,c],[c,a]]:
		var candidate := Geometry3D.get_closest_point_to_segment(point,segment[0],segment[1])
		if point.distance_squared_to(candidate)<point.distance_squared_to(result): result=candidate
	return result

func bind_name(layer,mi: MeshInstance3D,index: int) -> String:
	var named := String(mi.skin.get_bind_name(index))
	return named if named!="" else String(layer.drv.skel.get_bone_name(mi.skin.get_bind_bone(index)))

func _initialize() -> void: call_deferred("run")

func run() -> void:
	expect(FileAccess.file_exists("res://data/model_profile_3d.json"),"canonical model profile exists")
	var library = Motion.new()
	expect(library.load_data(),"hand-aware body library loads")
	for role: String in ["player","foe"]:
		var layer = Layer.new()
		root.add_child(layer)
		layer.configure(role,"res://assets/3d/"+role+"-rigged.glb",Layer.DEFAULT_SIDE_YAW if role=="player" else Layer.DEFAULT_FOE_YAW,false)
		var path := "res://data/motion_input.json" if role=="player" else "res://data/motion_input_foe.json"
		var legacy: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
		expect(layer.setup(legacy),role+" actual imported layer setup")
		expect(layer.drv!=null and layer.drv.skel.get_bone_count()==14,role+" original14bone rig retained")
		expect(layer._hand_meshes.size()==1,role+" one actual mesh exposes four hand morphs")
		expect(Hands.valid_profile(layer._hand_profile),role+" actual canonical socket profile valid")
		if layer._hand_meshes.size()!=1 or not Hands.valid_profile(layer._hand_profile):
			layer.free()
			continue
		var mi: MeshInstance3D = layer._hand_meshes[0].mi
		var mesh := mi.mesh as ArrayMesh
		expect(mesh.get_surface_count()==1 and mesh.get_blend_shape_count()==4,role+" one surface and four imported targets")
		var base := mesh.surface_get_arrays(0)
		var targets: Array = mesh.surface_get_blend_shape_arrays(0)
		var vertices: PackedVector3Array = base[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = base[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = base[Mesh.ARRAY_WEIGHTS]
		var indices: PackedInt32Array = base[Mesh.ARRAY_INDEX]
		var half_f: PackedVector3Array = targets[0][Mesh.ARRAY_VERTEX]
		var full_f: PackedVector3Array = targets[1][Mesh.ARRAY_VERTEX]
		var half_b: PackedVector3Array = targets[2][Mesh.ARRAY_VERTEX]
		var full_b: PackedVector3Array = targets[3][Mesh.ARRAY_VERTEX]
		# The canonical bridge fixes target order; inspect real arrays after import.
		for front: bool in [true,false]:
			var name := "forearm_f" if front else "forearm_b"
			var half: PackedVector3Array = half_f if front else half_b
			var full: PackedVector3Array = full_f if front else full_b
			var hand_vertices := {}
			for vertex in range(vertices.size()):
				var influence := 0.0
				for slot in range(4):
					var at := vertex*4+slot
					if weights[at]>0.0 and bind_name(layer,mi,bones[at])==name: influence+=weights[at]
				if influence>.9: hand_vertices[vertex]=true
			var hand_triangles := []
			for index in range(0,indices.size(),3):
				if hand_vertices.has(indices[index]) and hand_vertices.has(indices[index+1]) and hand_vertices.has(indices[index+2]):
					hand_triangles.append([indices[index],indices[index+1],indices[index+2]])
			expect(hand_triangles.size()>10,role+" "+name+" actual hand surface identified")
			for grip: float in [.0,.25,.5,.75,1.0]:
				var pose: Dictionary = library.sample(role,"jab",library.contact_frame(role,"jab"))
				pose.hand_grip=[grip,grip]
				layer.apply_visual({"pose":pose,"facing":1 if role=="player" else -1,"canvas_tilt":0.0})
				var coefficients := Hands.weights(grip)
				var globals: Dictionary = layer.drv.pose_global_transforms(pose)
				var deformed := {}
				for vertex: int in hand_vertices:
					var point := vertices[vertex]*coefficients.x+half[vertex]*coefficients.y+full[vertex]*coefficients.z
					if mesh.blend_shape_mode==Mesh.BLEND_SHAPE_MODE_RELATIVE:
						point=vertices[vertex]+half[vertex]*coefficients.y+full[vertex]*coefficients.z
					var skinned := Vector3.ZERO
					for slot in range(4):
						var at := vertex*4+slot
						if weights[at]<=0.0: continue
						var joint := bind_name(layer,mi,bones[at])
						if globals.has(joint): skinned+=(globals[joint]*mi.skin.get_bind_pose(bones[at])*point)*weights[at]
					deformed[vertex]=skinned
				var predicted: Vector3 = globals[name]*Hands.socket(layer._hand_profile,front,grip)
				var distance := INF
				for triangle: Array in hand_triangles:
					distance=minf(distance,predicted.distance_to(closest(predicted,deformed[triangle[0]],deformed[triangle[1]],deformed[triangle[2]])))
				max_socket_error=maxf(max_socket_error,distance)
				expect(distance<=.02,role+" "+name+" actual skinned hand socket g="+str(grip)+" distance="+str(distance))
				expect(layer.last_hand_grip==[grip,grip],role+" hand-only update reaches actual mesh")
		layer.free()
	for failure: String in failures: print("FAIL: ",failure)
	print("HAND ASSET CHECK: %d/%d passed socket_max_m=%f" % [total-failures.size(),total,max_socket_error])
	quit(0 if failures.is_empty() else 1)
