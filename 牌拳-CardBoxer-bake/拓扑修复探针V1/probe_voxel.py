"""可行性探针：不买 ZBrush，Blender 自带 Voxel Remesh 能否救回自动绑骨。

只回答一个问题：AI 生成模型的「2,809 个开放薄壳 -> Bone Heat 0 覆盖」，
用 Blender 5.2.3 自带的体素重建 + 降面 + Data Transfer 前置流程，
能不能让 ARMATURE_AUTO 从 0 覆盖率变成非 0。

边界（执行前声明）：
  * 只读 `对手怪Blender建模V1/对手怪V1.blend`，不写回、不改任何既有归档；
  * 不进 Godot、不渲动作帧、不改游戏源码；
  * 代理壳会丢失原 PBR / UV，渲图只用中性灰证明体块，不假装贴图还在；
  * 这是「要不要买软件」的证据，不是 #53 方向已选定。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"

VOXEL_SIZES = [0.020, 0.035]
DECIMATE_TARGET_FACES = 20000


def log(*a):
    print(*a, flush=True)


def count_shells(mesh):
    """按共享顶点索引做 union-find，与 GLB 侧 verify_shells.py 同口径。"""
    parent = list(range(len(mesh.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for poly in mesh.polygons:
        vs = poly.vertices
        for v in vs[1:]:
            union(vs[0], v)
    used = set()
    for poly in mesh.polygons:
        used.update(poly.vertices)
    return len({find(v) for v in used})


def bbox_of(obj):
    pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return ([round(min(p[i] for p in pts), 5) for i in range(3)],
            [round(max(p[i] for p in pts), 5) for i in range(3)])


def face_indices(mesh):
    return [list(p.vertices) for p in mesh.polygons]


def fresh_copy(src, name):
    obj = src.copy()
    obj.data = src.data.copy()
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    obj.vertex_groups.clear()
    obj.parent = None
    obj.hide_render = False
    return obj


def auto_weight(obj, rig):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    covered = sum(1 for v in obj.data.vertices
                  if any(g.weight > 1e-6 for g in v.groups))
    return {"groups": len(obj.vertex_groups),
            "covered": covered,
            "total": len(obj.data.vertices),
            "coverage": round(covered / max(1, len(obj.data.vertices)), 5)}


def voxel_remesh(obj, size):
    obj.data.remesh_voxel_size = size
    obj.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if bpy.ops.object.voxel_remesh.poll():
        bpy.ops.object.voxel_remesh()
        return "bpy.ops.object.voxel_remesh"
    mod = obj.modifiers.new("voxel_fallback", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = size
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return "REMESH modifier fallback"


def decimate_to(obj, target_faces):
    before = len(obj.data.polygons)
    if before <= target_faces:
        return {"applied": False, "faces_before": before, "faces_after": before}
    mod = obj.modifiers.new("decimate_for_heat", "DECIMATE")
    mod.ratio = target_faces / before
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return {"applied": True, "faces_before": before,
            "faces_after": len(obj.data.polygons)}


t0 = time.time()
assert BLEND.is_file(), f"missing {BLEND}"
blend_sha = hashlib.sha256(BLEND.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(BLEND))

src = next(o for o in bpy.context.scene.objects if o.type == "MESH")
rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
log(f"OPEN src={src.name} verts={len(src.data.vertices)} "
    f"faces={len(src.data.polygons)} rig={rig.name} bones={len(rig.data.bones)}")

raw = {"verts": len(src.data.vertices), "faces": len(src.data.polygons),
       "uv_layers": len(src.data.uv_layers),
       "materials": len(src.data.materials),
       "shells": count_shells(src.data),
       "bbox": bbox_of(src)}
log("RAW", raw)

report = {
    "blender": bpy.app.version_string,
    "source_blend": str(BLEND.name),
    "source_blend_sha256": blend_sha,
    "decimate_target_faces": DECIMATE_TARGET_FACES,
    "raw": raw,
    "cases": [],
}

# --- 对照 1：原封不动的碎壳网格，同口径跑一次自动权重 -----------------------
base = fresh_copy(src, "case_raw")
base_w = auto_weight(base, rig)
report["cases"].append({
    "case": "raw_no_remesh",
    "voxel_size": None,
    "operator": None,
    "after_remesh": {"verts": raw["verts"], "faces": raw["faces"],
                     "shells": raw["shells"]},
    "decimate": {"applied": False},
    "bbox": raw["bbox"],
    "auto_weight": base_w,
})
log("CASE raw_no_remesh", base_w)
base.hide_render = True

# --- 对照 2/3：体素重建 -> 降面 -> 自动权重 ---------------------------------
for i, size in enumerate(VOXEL_SIZES):
    tag = f"v{str(size).replace('.', 'p')}"
    obj = fresh_copy(src, f"case_{tag}")
    op = voxel_remesh(obj, size)
    after = {"verts": len(obj.data.vertices),
             "faces": len(obj.data.polygons),
             "shells": count_shells(obj.data)}
    log(f"REMESH {tag} op={op} {after}")
    dec = decimate_to(obj, DECIMATE_TARGET_FACES)
    post = {"verts": len(obj.data.vertices),
            "faces": len(obj.data.polygons),
            "shells": count_shells(obj.data)}
    log(f"DECIMATE {tag} {dec} -> {post}")
    w = auto_weight(obj, rig)
    log(f"AUTO_WEIGHT {tag} {w}")

    # 导出三角/多边形索引，供进程外独立 union-find 复核壳数
    (HERE / f"faces_{tag}.json").write_text(
        json.dumps(face_indices(obj.data)), encoding="ascii")

    report["cases"].append({
        "case": tag,
        "voxel_size": size,
        "operator": op,
        "after_remesh": after,
        "decimate": dec,
        "after_decimate": post,
        "bbox": bbox_of(obj),
        "auto_weight": w,
    })

    if i == 0:
        # 第一档渲一张正面图：只证明体块没被体素化糊掉，不假装 PBR 还在
        src.hide_render = True
        base.hide_render = True
        mat = bpy.data.materials.new("proxy_neutral_gray")
        mat.diffuse_color = (0.55, 0.57, 0.62, 1.0)
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        scene = bpy.context.scene
        scene.render.resolution_x = scene.render.resolution_y = 768
        scene.render.filepath = str(HERE / "proxy-front.png")
        bpy.ops.render.render(write_still=True)
        log("RENDER proxy-front.png", (HERE / "proxy-front.png").stat().st_size, "B")
    obj.hide_render = True

report["elapsed_seconds"] = round(time.time() - t0, 2)
(HERE / "voxel_probe.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
log("VOXEL_PROBE_OK", report["elapsed_seconds"], "s")
