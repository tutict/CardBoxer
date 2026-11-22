"""Isolate WHY Blender bone-heat weighting failed on the generated GLB.

Three controlled experiments, each on a freshly imported + normalized mesh:
    C1 minimal      : 3 bones entirely inside the torso.
    C2 scaled       : the game's 13 bones shrunk 50% around the hip.
    C3 apose        : a symmetric A-pose skeleton roughly inside the real mesh.
Then a bone-heat-free fallback (nearest-segment rigid weights) is tried and
actually driven by one pose-bone rotation, to see whether a fully automatic
binding path exists at all.

Also reports mesh topology, because disconnected shells are the usual reason
bone heat cannot solve.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GLB = HERE / "artifact_03.glb"
OUT_JSON = HERE / "rigfit2_result.json"

sys.path.insert(0, str(BAKE))
import boxer_rig  # noqa: E402

TARGET_HEIGHT = 1.72


def log(*a):
    print(*a, flush=True)


def fresh_mesh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(GLB))
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    s = TARGET_HEIGHT / (hi[2] - lo[2])
    cx, cy = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
    for o in objs:
        for v in o.data.vertices:
            v.co = Vector(((v.co.x - cx) * s,
                           (v.co.y - cy) * s,
                           (v.co.z - lo[2]) * s))
        o.data.update()
    return objs[0]


def topology(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bm.verts.ensure_lookup_table()
    edges = list(bm.edges)
    non_manifold = sum(1 for e in edges if not e.is_manifold)
    boundary = sum(1 for e in edges if e.is_boundary)
    seen = set()
    comp_sizes = []
    for start in bm.verts:
        if start.index in seen:
            continue
        stack, size = [start], 0
        seen.add(start.index)
        while stack:
            v = stack.pop()
            size += 1
            for e in v.link_edges:
                w = e.other_vert(v)
                if w.index not in seen:
                    seen.add(w.index)
                    stack.append(w)
        comp_sizes.append(size)
    comp_sizes.sort(reverse=True)
    out = {
        "verts": len(bm.verts), "faces": len(bm.faces), "edges": len(edges),
        "non_manifold_edges": non_manifold, "boundary_edges": boundary,
        "connected_components": len(comp_sizes),
        "component_sizes_top10": comp_sizes[:10],
        "component_singletons": sum(1 for c in comp_sizes if c == 1),
    }
    bm.free()
    return out


def build_arm(name, spec):
    data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, head, tail, parent in spec:
        eb = data.edit_bones.new(bone_name)
        eb.head = (head[0], 0.0, head[1])
        eb.tail = (tail[0], 0.0, tail[1])
        if parent:
            eb.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def bone_heat(mesh, arm):
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    err = None
    t = time.time()
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    names = {g.index: g.name for g in mesh.vertex_groups}
    covered = 0
    per_group = {}
    for v in mesh.data.vertices:
        if any(g.weight > 1e-6 for g in v.groups):
            covered += 1
        for g in v.groups:
            nm = names.get(g.group, "?")
            per_group[nm] = per_group.get(nm, 0) + 1
    return {
        "seconds": round(time.time() - t, 2),
        "error": err,
        "vertex_groups": len(names),
        "covered_vertices": covered,
        "total_vertices": len(mesh.data.vertices),
        "coverage": round(covered / max(len(mesh.data.vertices), 1), 4),
        "per_group": per_group,
    }


MINIMAL = [
    ("hips", (0.0, 0.80), (0.0, 0.98), None),
    ("spine", (0.0, 0.98), (0.0, 1.45), "hips"),
    ("head", (0.0, 1.45), (0.0, 1.72), "spine"),
]
SCALED = []
for nm, head, tail, parent in boxer_rig.BONES:
    h = (0.0 + (head[0] - 0.0) * 0.5, 0.80 + (head[1] - 0.80) * 0.5)
    t = (0.0 + (tail[0] - 0.0) * 0.5, 0.80 + (tail[1] - 0.80) * 0.5)
    SCALED.append((nm, h, t, parent))
APOSE = [
    ("hips", (0.00, 0.80), (0.00, 0.98), None),
    ("spine", (0.00, 0.98), (0.00, 1.22), "hips"),
    ("chest", (0.00, 1.22), (0.00, 1.48), "spine"),
    ("neck", (0.00, 1.48), (0.00, 1.62), "chest"),
    ("head", (0.00, 1.62), (0.00, 1.72), "neck"),
    ("upperarm_L", (0.16, 1.42), (0.30, 1.12), "chest"),
    ("forearm_L", (0.30, 1.12), (0.38, 0.86), "upperarm_L"),
    ("upperarm_R", (-0.16, 1.42), (-0.30, 1.12), "chest"),
    ("forearm_R", (-0.30, 1.12), (-0.38, 0.86), "upperarm_R"),
    ("thigh_L", (0.09, 0.80), (0.12, 0.42), "hips"),
    ("shin_L", (0.12, 0.42), (0.15, 0.02), "thigh_L"),
    ("thigh_R", (-0.09, 0.80), (-0.12, 0.42), "hips"),
    ("shin_R", (-0.12, 0.42), (-0.15, 0.02), "thigh_R"),
]

results = {}
log("TOPOLOGY", topology(fresh_mesh()))

for label, spec in (("C1_minimal", MINIMAL), ("C2_scaled", SCALED), ("C3_apose", APOSE)):
    mesh = fresh_mesh()
    arm = build_arm(label, spec)
    res = bone_heat(mesh, arm)
    results[label] = res
    log("BONE_HEAT", label, "groups=", res["vertex_groups"],
        "coverage=", res["coverage"], "seconds=", res["seconds"],
        "error=", res["error"])

# ---- bone-heat-free fallback: nearest-segment rigid weights --------------
mesh = fresh_mesh()
arm = build_arm("fallback", boxer_rig.BONES)
segments = {}
for nm, head, tail, _p in boxer_rig.BONES:
    segments[nm] = (Vector((head[0], 0.0, head[1])),
                    Vector((tail[0], 0.0, tail[1])))


def seg_distance(p, a, b):
    d = b - a
    t = max(0.0, min(1.0, (p - a).dot(d) / max(d.length_squared, 1e-9)))
    return (p - (a + d * t)).length


groups = {nm: mesh.vertex_groups.new(name=nm) for nm in segments}
t_fb = time.time()
for v in mesh.data.vertices:
    ds = sorted((seg_distance(v.co, a, b), nm) for nm, (a, b) in segments.items())
    d0, n0 = ds[0]
    d1, n1 = ds[1]
    w0 = 1.0 / (d0 + 0.03)
    w1 = 1.0 / (d1 + 0.03) if d1 < d0 * 1.6 else 0.0
    total = w0 + w1
    groups[n0].add([v.index], w0 / total, "REPLACE")
    if w1 > 0.0:
        groups[n1].add([v.index], w1 / total, "REPLACE")
fb_seconds = round(time.time() - t_fb, 2)

mesh.parent = arm
mod = mesh.modifiers.new("Armature", "ARMATURE")
mod.object = arm

pb = arm.pose.bones["upperarm_f"]
pb.rotation_mode = "XYZ"
pb.rotation_euler.z = math.radians(35)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
ev = mesh.evaluated_get(dg)
ev_mesh = ev.to_mesh()
disp = [(ev_mesh.vertices[i].co - mesh.data.vertices[i].co).length
        for i in range(len(mesh.data.vertices))]
fallback = {
    "weights_seconds": fb_seconds,
    "vertex_groups": len(mesh.vertex_groups),
    "weighted_vertices": len(mesh.data.vertices),
    "coverage": 1.0,
    "rotation_deg": 35,
    "pose_bone": "upperarm_f",
    "max_displacement_m": round(max(disp), 5),
    "mean_displacement_m": round(sum(disp) / len(disp), 5),
    "moved_vertices_gt_1cm": sum(1 for d in disp if d > 0.01),
}
ev.to_mesh_clear()
log("FALLBACK", fallback)
results["C4_nearest_segment_rigid"] = fallback

out = {
    "blender": bpy.app.version_string,
    "topology": topology(fresh_mesh()),
    "experiments": results,
}
OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
log("RIGFIT2_OK")
