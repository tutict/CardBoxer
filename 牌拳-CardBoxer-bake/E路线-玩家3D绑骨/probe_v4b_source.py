"""E 路线源资产探针：把玩家 V4b GLB 变成可直接打开/驱动的 Blender 源 .blend。

与 A 路线源（对手怪V1.blend）对齐的四件事：
  · 归一化到 1.72 m 高、脚底 z=0、x/y 居中（同 render_character.py 公式）；
  · 3 张 embedded PBR 全部 pack 进 .blend，不依赖外部临时路径；
  · 场景里必须有 CAMERA + 灯，否则 C.setup_camera / 渲染链会崩；
  · 只读源 GLB，不回写 3D模型探针V4b/ 归档。

用法：blender.exe -b --python probe_v4b_source.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GLB = BAKE / "3D模型探针V4b" / "artifact_03.glb"
OUT_BLEND = HERE / "玩家V4b-源.blend"
OUT_JSON = HERE / "source_probe.json"
FRONT = HERE / "frames" / "e-source-front.png"
TARGET_HEIGHT = 1.72


def log(*a):
    print(*a, flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bounds(meshes):
    pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi, len(pts)


def shell_count(mesh):
    n = len(mesh.vertices)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in mesh.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[b] = a
    return len({find(i) for i in range(n)})


def texture_inventory(meshes):
    out = []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.use_nodes:
                for n in mat.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        out.append({
                            "image": n.image.name,
                            "size": list(n.image.size),
                            "packed": bool(n.image.packed_file),
                            "source": n.image.source,
                        })
    return out


def add_stage(scene):
    world = bpy.data.worlds.new("e_world")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.59, 0.68, 1.0)
    bg.inputs["Strength"].default_value = 0.80
    scene.world = world

    sun_data = bpy.data.lights.new("e_key", "SUN")
    sun_data.energy = 2.2
    sun = bpy.data.objects.new("e_key", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(30), math.radians(-36),
                          math.radians(22))

    fill_data = bpy.data.lights.new("e_fill", "AREA")
    fill_data.energy = 260
    fill_data.shape = "DISK"
    fill_data.size = 5.0
    fill = bpy.data.objects.new("e_fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (-2.2, -3.0, 2.6)
    fill.rotation_euler = (Vector((0, 0, 1.2)) - fill.location
                           ).to_track_quat("-Z", "Y").to_euler()

    cam_data = bpy.data.cameras.new("e_cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.30
    cam = bpy.data.objects.new("e_cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -4.0, 0.86)
    cam.rotation_euler = (Vector((0.0, 0.0, 0.86)) - cam.location
                          ).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    return cam


def main() -> int:
    t0 = time.time()
    assert GLB.is_file(), GLB
    glb_sha = sha256(GLB)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(GLB))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    assert meshes, "no mesh imported"
    log(f"IMPORT meshes={len(meshes)} names={[o.name for o in meshes]}")

    raw_lo, raw_hi, nverts = bounds(meshes)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    lo, hi, _ = bounds(meshes)
    height = hi[2] - lo[2]
    scale = TARGET_HEIGHT / height
    cx, cy = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
    for o in meshes:
        for v in o.data.vertices:
            v.co = Vector(((v.co.x - cx) * scale,
                           (v.co.y - cy) * scale,
                           (v.co.z - lo[2]) * scale))
        o.data.update()
    nlo, nhi, _ = bounds(meshes)
    log(f"NORMALIZE scale={scale:.6f} raw_height={height:.5f} "
        f"bbox={[round(v, 4) for v in nlo]}..{[round(v, 4) for v in nhi]}")

    bpy.ops.file.pack_all()
    tex = texture_inventory(meshes)
    shell = shell_count(meshes[0].data)
    struct = {
        "verts": nverts,
        "faces": sum(len(o.data.polygons) for o in meshes),
        "shells": shell,
        "uv_layers": sum(len(o.data.uv_layers) for o in meshes),
        "materials": sum(len(o.data.materials) for o in meshes),
        "textures": tex,
        "packed_textures": sum(1 for t in tex if t["packed"]),
    }
    log("STRUCT " + json.dumps(struct, ensure_ascii=False)[:500])

    add_stage(scene)
    FRONT.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(FRONT)
    bpy.ops.render.render(write_still=True)
    front_bytes = FRONT.read_bytes()
    assert front_bytes[:8] == b"\x89PNG\r\n\x1a\n" and len(front_bytes) > 10000

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND), compress=True)
    blend_bytes = OUT_BLEND.read_bytes()
    report = {
        "blender": bpy.app.version_string,
        "glb": {"path": str(GLB), "bytes": GLB.stat().st_size,
                "sha256": glb_sha},
        "raw_bbox": {"min": [round(v, 5) for v in raw_lo],
                     "max": [round(v, 5) for v in raw_hi]},
        "normalize": {"target_height_m": TARGET_HEIGHT,
                      "scale": round(scale, 6),
                      "bbox_min": [round(v, 5) for v in nlo],
                      "bbox_max": [round(v, 5) for v in nhi]},
        "structure": struct,
        "stage": {"camera": scene.camera.name,
                  "lights": sorted(o.name for o in scene.objects
                                   if o.type == "LIGHT")},
        "front_render": {"file": FRONT.name, "bytes": len(front_bytes),
                         "sha256": hashlib.sha256(front_bytes).hexdigest()},
        "source_blend": {"file": OUT_BLEND.name, "bytes": len(blend_bytes),
                         "sha256": sha256(OUT_BLEND)},
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    log(f"SOURCE_PROBE_OK verts={nverts} shells={shell} "
        f"packed={struct['packed_textures']}/{len(tex)} "
        f"blend={len(blend_bytes)}B elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
