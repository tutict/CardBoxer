"""Render one generated GLB through a FIXED camera set so V3 and V4 are comparable.

Key decision: the engineer picked the PBR service preview (artifact_02.png),
NOT our toon portrait. So this renderer KEEPS the original PBR materials and
uses identical cameras/lights for both models. No toon shader, no outline --
those would hide exactly the facial detail we are being asked to improve.

Usage (Blender):
  blender --background --python render_character.py -- --glb <abs path> --prefix v3
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--glb", required=True)
ap.add_argument("--prefix", required=True)
args = ap.parse_args(argv)

GLB = Path(args.glb)
assert GLB.is_file(), f"missing GLB: {GLB}"
assert GLB.read_bytes()[:4] == b"glTF", f"not a GLB: {GLB}"

TARGET_HEIGHT = 1.72
SHOTS = [
    # full body, same framing as V3's zzz-*.png
    ("front", 0, 0.86, 2.30, 768),
    ("angle25", 25, 0.86, 2.30, 768),
    ("angle55", 55, 0.86, 2.30, 768),
    ("back35", -35, 0.86, 2.30, 768),
    # NEW for V4: face and upper-body close-ups, same cameras on V3 and V4
    ("face-front", 0, 1.55, 0.46, 1024),
    ("face-25", 25, 1.55, 0.46, 1024),
    ("upper", 0, 1.24, 1.00, 1024),
]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert meshes, "no mesh imported"
print(f"IMPORT glb={GLB.name} meshes={len(meshes)}", flush=True)

# --- normalize: identical to render_zzz.py so framing matches across versions
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
print(f"NORMALIZE scale={scale:.6f} raw_height={hi[2]-lo[2]:.4f}", flush=True)

# --- lighting: moderate, no blown whites ---------------------------------
scene = bpy.context.scene
world = bpy.data.worlds.new("v4_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.59, 0.68, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.80
scene.world = world

sun_data = bpy.data.lights.new("v4_key", "SUN")
sun_data.energy = 2.2
sun = bpy.data.objects.new("v4_key", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(30), math.radians(-36), math.radians(22))

fill_data = bpy.data.lights.new("v4_fill", "AREA")
fill_data.energy = 260
fill_data.shape = "DISK"
fill_data.size = 5.0
fill = bpy.data.objects.new("v4_fill", fill_data)
scene.collection.objects.link(fill)
fill.location = (-2.2, -3.0, 2.6)
fill.rotation_euler = (Vector((0, 0, 1.2)) - fill.location).to_track_quat("-Z", "Y").to_euler()

cam_data = bpy.data.cameras.new("v4_cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("v4_cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

scene.render.engine = "BLENDER_EEVEE"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "Standard"

R = 4.0
t0 = time.time()
outputs = []
for name, deg, tz, ortho, res in SHOTS:
    a = math.radians(deg)
    cam.location = (R * math.sin(a), -R * math.cos(a), tz)
    cam.rotation_euler = (Vector((0.0, 0.0, tz)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = ortho
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    path = HERE / f"{args.prefix}-{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    outputs.append({"shot": name, "angle_deg": deg, "target_z": tz,
                    "ortho_scale": ortho, "resolution": res,
                    "file": path.name, "bytes": path.stat().st_size})
    print(f"RENDER {path.name} {path.stat().st_size} B", flush=True)

report = {
    "blender": bpy.app.version_string,
    "glb": GLB.name,
    "glb_sha256": __import__("hashlib").sha256(GLB.read_bytes()).hexdigest(),
    "prefix": args.prefix,
    "material_policy": "original PBR kept (engineer picked the PBR service preview)",
    "normalize_scale": round(scale, 6),
    "raw_height_m": round(hi[2] - lo[2], 5),
    "shots": outputs,
    "elapsed_seconds": round(time.time() - t0, 2),
}
(HERE / f"render_{args.prefix}.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"RENDER_OK prefix={args.prefix} shots={len(outputs)} "
      f"elapsed={report['elapsed_seconds']}s", flush=True)
