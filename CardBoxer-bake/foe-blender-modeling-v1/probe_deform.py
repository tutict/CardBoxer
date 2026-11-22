"""刚性权重的承重验证：把一根手臂骨转 35°，量顶点到底动没动、动多少。

`foe_blender_build.py` 声称「挂了 13 骨 + 100% 刚性权重，链路可动」。
这条只证明「可动」，**不证明变形可用**：A-pose 模型对格斗站架骨架、
2,809 个开放薄壳，一动很可能撕成碎片。这里给出可复算的位移数字和
一张驱动后的图，把「不证明可用」从口头变成证据。

打开已保存的 .blend，在内存里变形，不回写 .blend、不写进 Godot。
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BLEND = HERE / "foe-V1.blend"
assert BLEND.is_file(), f"missing {BLEND}"
ANGLE_DEG = 35
BONE = "upperarm_f"

t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
arm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
assert meshes and arm, "blend is missing mesh or armature"
assert BONE in arm.pose.bones, f"missing pose bone {BONE}"
print(f"OPEN meshes={len(meshes)} arm={arm.name} bones={len(arm.pose.bones)}", flush=True)


def evaluated_positions():
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        m = ev.to_mesh()
        out.extend([(ev.matrix_world @ v.co).copy() for v in m.vertices])
        ev.to_mesh_clear()
    return out


rest = evaluated_positions()
pb = arm.pose.bones[BONE]
pb.rotation_mode = "XYZ"
pb.rotation_euler[2] = math.radians(ANGLE_DEG)
bpy.context.view_layer.update()
driven = evaluated_positions()
assert len(rest) == len(driven), "vertex count changed under armature"

deltas = [(a - b).length for a, b in zip(rest, driven)]
moved = sum(1 for d in deltas if d > 1e-4)
result = {
    "blend": BLEND.name,
    "bone": BONE,
    "angle_deg": ANGLE_DEG,
    "axis": "pose-bone local Z",
    "vertices": len(deltas),
    "moved_vertices_gt_0_1mm": moved,
    "moved_ratio": round(moved / len(deltas), 5),
    "max_displacement_m": round(max(deltas), 5),
    "mean_displacement_m": round(sum(deltas) / len(deltas), 5),
    "weight_mode": "nearest-segment rigid 1.0 (from foe_blender_build.py)",
    "caveat": "链路可动，不证明变形可用；刚性权重会把开放薄壳整片带走",
}
print(json.dumps(result, ensure_ascii=False), flush=True)

scene = bpy.context.scene
scene.render.filepath = str(HERE / "foe-deform-upperarm35.png")
bpy.ops.render.render(write_still=True)
png = HERE / "foe-deform-upperarm35.png"
result["render"] = {"file": png.name, "bytes": png.stat().st_size}
result["elapsed_seconds"] = round(time.time() - t0, 2)
(HERE / "deform_probe.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"DEFORM_OK elapsed={result['elapsed_seconds']}s", flush=True)
