"""Blender-side feasibility probe for the generated anime-style boxer GLB.

Question this answers (NOT "does it look nice"):
    Can the static generated mesh actually be driven by the game's existing
    13-bone rig / 228-frame baked2.json joint table?

Measured, in Blender 5.2.3 headless:
    1. GLB imports, UV layers exist, embedded PBR textures really load.
    2. World bbox, axis orientation, and normalization to the game's 1.72 m height.
    3. How far each REST joint of boxer_rig sits from the nearest mesh vertex.
       (A-pose mesh vs fighting-stance rest skeleton => large distances.)
    4. Whether Blender's automatic bone-heat weights run at all on this mesh.
    5. An overlay PNG showing the REST skeleton projected over the model.

Nothing here writes into the Godot game. Output: rigfit_result.json + PNG.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
# V1~V3 教训：服务返回 URL 的编号顺序会变（V2 是 01.png / 02.zip / 03.glb），
# 一律按文件魔数找 GLB，不按编号硬编码。V3 探针仍硬编码 03，本版修掉。
GLB = next((p for p in sorted(HERE.glob("artifact_*"))
            if p.is_file() and p.read_bytes()[:4] == b"glTF"), None)
assert GLB is not None, "no GLB found by magic bytes"
OUT_JSON = HERE / "rigfit_result.json"
OUT_PNG = HERE / "rigfit_overlay.png"

sys.path.insert(0, str(BAKE))
import boxer_rig  # noqa: E402  (pure constants + bpy import at module top)

TARGET_HEIGHT = 1.72  # boxer_rig.REST["head"][1], in metres (= 172 game px)


def log(*args):
    print(*args, flush=True)


def emissive(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def world_bounds(objs):
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return (
        [min(p[i] for p in pts) for i in range(3)],
        [max(p[i] for p in pts) for i in range(3)],
        len(pts),
    )


t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
log("IMPORT meshes=", len(meshes),
    "names=", [o.name for o in meshes][:8],
    "objects=", len(bpy.context.scene.objects))

if not meshes:
    log("RIGFIT_FAILED no mesh imported")
    raise SystemExit(2)

raw_min, raw_max, raw_verts = world_bounds(meshes)
log("RAW_BBOX min=", [round(v, 4) for v in raw_min],
    "max=", [round(v, 4) for v in raw_max], "verts=", raw_verts)

# --- materials / textures -------------------------------------------------
textures = []
for ob in meshes:
    for slot in ob.material_slots:
        mat = slot.material
        if not mat:
            continue
        if not mat.use_nodes:
            textures.append({"material": mat.name, "nodes": False})
            continue
        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE":
                continue
            img = node.image
            size = None
            if img is not None:
                try:
                    size = list(img.size)
                except Exception:
                    size = None
            linked = sorted({link.to_socket.name
                             for link in mat.node_tree.links
                             if link.from_node == node})
            textures.append({
                "material": mat.name,
                "image": img.name if img else None,
                "size": size,
                "filepath": (img.filepath or "")[:120] if img else "",
                "linked_to": linked,
            })
uv_layers = sum(len(o.data.uv_layers) for o in meshes)
log("TEXTURES", len(textures), "loaded=", sum(1 for t in textures if t.get("size")),
    "uv_layers=", uv_layers)
for t in textures:
    log("  ", t)

# --- bake world transform, normalize to the game's scale ------------------
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

bmin, bmax, _ = world_bounds(meshes)
height = bmax[2] - bmin[2]
scale = TARGET_HEIGHT / height
cx = (bmin[0] + bmax[0]) / 2.0
cy = (bmin[1] + bmax[1]) / 2.0
for o in meshes:
    for v in o.data.vertices:
        v.co = Vector(((v.co.x - cx) * scale,
                       (v.co.y - cy) * scale,
                       (v.co.z - bmin[2]) * scale))
    o.data.update()

nmin, nmax, nverts = world_bounds(meshes)
log("NORMALIZED scale=", round(scale, 6),
    "min=", [round(v, 4) for v in nmin],
    "max=", [round(v, 4) for v in nmax], "verts=", nverts)

verts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]

# --- quantitative mismatch: REST joints vs model geometry ----------------
def nearest(p):
    return min((v - p).length for v in verts)


joint_distance = {}
for name, (gx, gz) in boxer_rig.REST.items():
    p = Vector((gx, 0.0, gz))
    joint_distance[name] = round(nearest(p), 4)

outside = [n for n, d in joint_distance.items() if d > 0.12]
log("REST_JOINT_NEAREST_VERTEX_M", joint_distance)
log("JOINTS_OUTSIDE_GEOMETRY(>0.12m)", len(outside), outside)


def x_width_at(z0, dz=0.05):
    xs = [v.x for v in verts if abs(v.z - z0) <= dz]
    if not xs:
        return None
    return {"z": z0, "xmin": round(min(xs), 4), "xmax": round(max(xs), 4),
            "vertices": len(xs)}


widths = {
    "at_rest_f_hand_z": x_width_at(1.56),
    "at_rest_head_z": x_width_at(1.72),
    "at_rest_hip_z": x_width_at(0.80),
    "at_rest_foot_z": x_width_at(0.0, 0.06),
}
max_abs_x_v = max(verts, key=lambda v: abs(v.x))
log("WIDTHS", widths)
log("MODEL_MAX_ABS_X", round(max_abs_x_v.x, 4),
    "at_z=", round(max_abs_x_v.z, 4))

# --- a clean 13-bone armature (no IK targets, no constraints) ------------
arm_data = bpy.data.armatures.new("probe_rig")
arm = bpy.data.objects.new("probe_rig", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for name, head, tail, parent in boxer_rig.BONES:
    eb = arm_data.edit_bones.new(name)
    eb.head = (head[0], 0.0, head[1])
    eb.tail = (tail[0], 0.0, tail[1])
    if parent:
        eb.parent = arm_data.edit_bones[parent]
bpy.ops.object.mode_set(mode="OBJECT")
log("ARMATURE bones=", len(arm_data.bones), "names=", list(arm_data.bones.keys()))

# --- visible overlay: bones + joints projected in front of the mesh -------
front_y = nmin[1] - 0.06
mat_bone = emissive("overlay_bone", (0.92, 0.12, 0.14))
mat_joint = emissive("overlay_joint", (0.05, 0.75, 0.85))
marker_objs = []
for name, head, tail, _parent in boxer_rig.BONES:
    a = Vector((head[0], front_y, head[1]))
    b = Vector((tail[0], front_y, tail[1]))
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.007,
                                        depth=d.length, location=(a + b) / 2.0)
    cyl = bpy.context.object
    cyl.name = "overlay_bone_" + name
    cyl.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    cyl.data.materials.append(mat_bone)
    marker_objs.append(cyl)
for name, (gx, gz) in boxer_rig.REST.items():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8,
                                         radius=0.019,
                                         location=(gx, front_y - 0.005, gz))
    sph = bpy.context.object
    sph.name = "overlay_joint_" + name
    sph.data.materials.append(mat_joint)
    marker_objs.append(sph)
log("OVERLAY markers=", len(marker_objs), "front_y=", round(front_y, 4))

# --- render overlay -------------------------------------------------------
scene = bpy.context.scene
world = bpy.data.worlds.new("probe_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.88, 0.89, 0.91, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
scene.world = world

sun_data = bpy.data.lights.new("probe_sun", "SUN")
sun_data.energy = 2.0
sun = bpy.data.objects.new("probe_sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(28), math.radians(-34), math.radians(24))

cam_data = bpy.data.cameras.new("probe_cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 2.30
cam = bpy.data.objects.new("probe_cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -3.0, 0.86)
cam.rotation_euler = (Vector((0.0, 0.0, 0.86)) - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.filepath = str(OUT_PNG)
bpy.ops.render.render(write_still=True)
log("OVERLAY_PNG", OUT_PNG.name, OUT_PNG.stat().st_size, "B")

# --- automatic bone-heat weights on the real mesh ------------------------
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
auto_error = None
t_auto = time.time()
try:
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
except Exception as exc:  # Blender may raise or only warn on stdout
    auto_error = f"{type(exc).__name__}: {exc}"
auto_seconds = round(time.time() - t_auto, 2)
log("AUTO_WEIGHT seconds=", auto_seconds, "error=", auto_error)

group_counts = {}
covered = 0
weighted_total = 0
for o in meshes:
    names = {g.index: g.name for g in o.vertex_groups}
    mods = [m.type for m in o.modifiers]
    for v in o.data.vertices:
        weighted_total += 1
        if any(ge.weight > 1e-6 for ge in v.groups):
            covered += 1
        for ge in v.groups:
            nm = names.get(ge.group, "?")
            group_counts[nm] = group_counts.get(nm, 0) + 1
log("VERTEX_GROUPS", len(group_counts),
    "covered=", covered, "/", weighted_total,
    "coverage=", round(covered / max(weighted_total, 1), 4))
log("GROUP_COUNTS", group_counts)

result = {
    "blender": bpy.app.version_string,
    "glb": str(GLB.name),
    "import": {
        "mesh_objects": len(meshes),
        "mesh_names": [o.name for o in meshes],
        "vertices_raw": raw_verts,
        "bbox_raw_min": [round(v, 5) for v in raw_min],
        "bbox_raw_max": [round(v, 5) for v in raw_max],
        "uv_layers": uv_layers,
        "textures": textures,
    },
    "normalization": {
        "target_height_m": TARGET_HEIGHT,
        "scale": round(scale, 6),
        "bbox_min": [round(v, 5) for v in nmin],
        "bbox_max": [round(v, 5) for v in nmax],
    },
    "pose_mismatch": {
        "rest_joint_nearest_vertex_m": joint_distance,
        "joints_outside_0_12m": outside,
        "outside_count": len(outside),
        "x_width_by_z": widths,
        "model_max_abs_x": round(max_abs_x_v.x, 4),
        "model_max_abs_x_at_z": round(max_abs_x_v.z, 4),
        "rest_f_hand_x": boxer_rig.REST["f_hand"][0],
        "rest_f_hand_z": boxer_rig.REST["f_hand"][1],
    },
    "automatic_weights": {
        "seconds": auto_seconds,
        "error": auto_error,
        "vertex_groups": len(group_counts),
        "group_counts": group_counts,
        "covered_vertices": covered,
        "total_vertices": weighted_total,
        "coverage": round(covered / max(weighted_total, 1), 4),
    },
    "overlay_png": OUT_PNG.name,
    "elapsed_seconds": round(time.time() - t0, 2),
}
OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
log("RIGFIT_OK elapsed=", result["elapsed_seconds"], "s")
