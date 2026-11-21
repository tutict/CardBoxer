"""Blender 建模：把图生 3D 产物组装成一份可编辑的 .blend 资产。

这一步不是「导入看一眼」：
  1. 导入 GLB（按魔数找，不按编号），量测原始结构；
  2. 归一化到《牌拳》坐标桥：身高 1.72 m、脚底 z=0、x/y 居中；
  3. 用游戏自己的 boxer_rig.BONES 建 13 骨 Armature；
  4. 给每个顶点按「最近骨骼段」赋刚性权重 1.0（对开放薄壳模型，
     Bone Heat 已知是 0 覆盖，这是可动的兜底而非可用变形）；
  5. 保存 .blend（模型 + 骨架 + 权重 + 相机灯光），渲四视角与上半身特写，
     保留生成模型自带 PBR，不加 toon / 描边。

如实边界：刚性权重证明「链路可动」，不证明变形可用；A-pose 模型对
格斗站架骨架本来就不对齐。本脚本不写进 Godot，不渲动作帧。
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE))
import boxer_rig  # noqa: E402

GLB = next((p for p in sorted(HERE.glob("artifact_*"))
            if p.is_file() and p.read_bytes()[:4] == b"glTF"), None)
assert GLB is not None, "no GLB found by magic bytes"

TARGET_HEIGHT = 1.72
SHOTS = [
    ("front", 0, 0.86, 2.30, 768),
    ("angle25", 25, 0.86, 2.30, 768),
    ("angle55", 55, 0.86, 2.30, 768),
    ("back35", -35, 0.86, 2.30, 768),
    ("upper", 0, 1.24, 1.00, 1024),
]


def log(*a):
    print(*a, flush=True)


t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert meshes, "no mesh imported"
log(f"IMPORT glb={GLB.name} meshes={len(meshes)}")

# --- 原始结构 -------------------------------------------------------------
raw_verts = sum(len(o.data.vertices) for o in meshes)
raw_tris = sum(len(o.data.polygons) for o in meshes)
uv_layers = sum(len(o.data.uv_layers) for o in meshes)
images = []
for o in meshes:
    for slot in o.material_slots:
        mat = slot.material
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    images.append({"name": n.image.name, "size": list(n.image.size)})
raw_pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
lo = [min(p[i] for p in raw_pts) for i in range(3)]
hi = [max(p[i] for p in raw_pts) for i in range(3)]
log(f"RAW verts={raw_verts} tris={raw_tris} uv_layers={uv_layers} "
    f"textures={len(images)} bbox={[round(v,4) for v in lo]}..{[round(v,4) for v in hi]}")

# --- 归一化（与 render_character.py 逐行同口径，保证能跟玩家 V4b 比）------
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
lo = [min(p[i] for p in pts) for i in range(3)]
hi = [max(p[i] for p in pts) for i in range(3)]
scale = TARGET_HEIGHT / (hi[2] - lo[2])
cx, cy = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
for o in meshes:
    for v in o.data.vertices:
        v.co = Vector(((v.co.x - cx) * scale,
                       (v.co.y - cy) * scale,
                       (v.co.z - lo[2]) * scale))
    o.data.update()
nmin = [min((o.matrix_world @ v.co)[i] for o in meshes for v in o.data.vertices)
        for i in range(3)]
nmax = [max((o.matrix_world @ v.co)[i] for o in meshes for v in o.data.vertices)
        for i in range(3)]
log(f"NORMALIZE scale={scale:.6f} min={[round(v,4) for v in nmin]} "
    f"max={[round(v,4) for v in nmax]}")

# --- 游戏自己的 13 骨 Armature -------------------------------------------
arm_data = bpy.data.armatures.new("foe_rig")
arm = bpy.data.objects.new("foe_rig", arm_data)
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
log(f"ARMATURE bones={len(arm_data.bones)} names={list(arm_data.bones.keys())}")

# --- 刚性权重兜底：每顶点归到最近骨骼段 ----------------------------------
segments = []
for name, head, tail, _ in boxer_rig.BONES:
    segments.append((name, Vector((head[0], 0.0, head[1])),
                     Vector((tail[0], 0.0, tail[1]))))


def seg_dist(p, a, b):
    ab = b - a
    d = ab.length_squared
    t = max(0.0, min(1.0, (p - a).dot(ab) / d)) if d > 1e-12 else 0.0
    return (p - (a + t * ab)).length


assigned = 0
per_bone = {name: 0 for name, _, _ in segments}
for o in meshes:
    groups = {name: o.vertex_groups.new(name=name) for name, _, _ in segments}
    buckets = {name: [] for name, _, _ in segments}
    for v in o.data.vertices:
        p = o.matrix_world @ v.co
        best = min(segments, key=lambda s: seg_dist(p, s[1], s[2]))[0]
        buckets[best].append(v.index)
        assigned += 1
        per_bone[best] += 1
    for name, idx in buckets.items():
        if idx:
            groups[name].add(idx, 1.0, "REPLACE")
    mod = o.modifiers.new("foe_armature", "ARMATURE")
    mod.object = arm
log(f"RIGID_WEIGHTS assigned={assigned}/{raw_verts} "
    f"coverage={round(assigned / raw_verts, 5)}")
log("PER_BONE", per_bone)

# --- 场景：灯光 + 正交相机（与玩家 V4b 同参数）----------------------------
scene = bpy.context.scene
world = bpy.data.worlds.new("foe_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.59, 0.68, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.80
scene.world = world

sun_data = bpy.data.lights.new("foe_key", "SUN")
sun_data.energy = 2.2
sun = bpy.data.objects.new("foe_key", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(30), math.radians(-36), math.radians(22))

fill_data = bpy.data.lights.new("foe_fill", "AREA")
fill_data.energy = 260
fill_data.shape = "DISK"
fill_data.size = 5.0
fill = bpy.data.objects.new("foe_fill", fill_data)
scene.collection.objects.link(fill)
fill.location = (-2.2, -3.0, 2.6)
fill.rotation_euler = (Vector((0, 0, 1.2)) - fill.location).to_track_quat("-Z", "Y").to_euler()

cam_data = bpy.data.cameras.new("foe_cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("foe_cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

scene.render.engine = "BLENDER_EEVEE"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "Standard"

outputs = []
R = 4.0
for name, deg, tz, ortho, res in SHOTS:
    a = math.radians(deg)
    cam.location = (R * math.sin(a), -R * math.cos(a), tz)
    cam.rotation_euler = (Vector((0.0, 0.0, tz)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = ortho
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    path = HERE / f"foe-{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    outputs.append({"shot": name, "angle_deg": deg, "target_z": tz,
                    "ortho_scale": ortho, "resolution": res,
                    "file": path.name, "bytes": path.stat().st_size})
    log(f"RENDER {path.name} {path.stat().st_size} B")

# 保存可编辑资产：把相机停回正面，打开 .blend 直接能渲
cam.location = (0.0, -R, 0.86)
cam.rotation_euler = (Vector((0.0, 0.0, 0.86)) - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.ortho_scale = 2.30
scene.render.resolution_x = scene.render.resolution_y = 768
scene.render.filepath = str(HERE / "foe-front.png")
blend = HERE / "对手怪V1.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
log(f"SAVED {blend.name} {blend.stat().st_size} B")

report = {
    "blender": bpy.app.version_string,
    "glb": GLB.name,
    "glb_sha256": hashlib.sha256(GLB.read_bytes()).hexdigest(),
    "mode": "image-to-3D -> Blender build",
    "raw": {"verts": raw_verts, "tris": raw_tris, "uv_layers": uv_layers,
            "textures": images, "bbox_min": [round(v, 5) for v in lo],
            "bbox_max": [round(v, 5) for v in hi]},
    "normalize": {"target_height_m": TARGET_HEIGHT, "scale": round(scale, 6),
                  "bbox_min": [round(v, 5) for v in nmin],
                  "bbox_max": [round(v, 5) for v in nmax]},
    "armature": {"bones": len(arm_data.bones), "source": "boxer_rig.BONES",
                 "weight_mode": "nearest-segment rigid 1.0",
                 "assigned": assigned, "total": raw_verts,
                 "coverage": round(assigned / raw_verts, 5),
                 "per_bone": per_bone},
    "material_policy": "original PBR kept (no toon / no outline)",
    "shots": outputs,
    "blend_file": {"file": blend.name, "bytes": blend.stat().st_size},
    "elapsed_seconds": round(time.time() - t0, 2),
}
(HERE / "blender_build.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"BUILD_OK shots={len(outputs)} elapsed={report['elapsed_seconds']}s")
