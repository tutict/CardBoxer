"""闭环探针：代理壳算出的平滑权重，能否传回原始高模且保住 PBR 贴图。

probe_voxel.py 证明了「体素代理壳 -> 自动权重 0% 变 99.96%」，
但代理壳表面被体素化溶蚀，不能当渲染资产。社区标准是
Voxel Proxy + Data Transfer：只借代理壳的权重，最终仍渲原高模。

本脚本在同一 .blend、同一相机、同一 35° 驱动下做 A/B 对照：
  A = 11-08 的「最近骨骼刚性权重」（已知最大位移 0.47922 m、会撕裂）
  B = 代理壳平滑权重经 Data Transfer 传回原高模后
同时检查 B 的 UV 层数 / 材质 / 3 张 PBR 贴图是否与原件一致。

边界：只读 .blend、不回写、不进 Godot、不改游戏源码、不改既有归档。
不声称「变形已经可用」，只给出可复算数字与两张同条件图，看图由人判。
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "foe-blender-modeling-v1" / "foe-V1.blend"
VOXEL_SIZE = 0.020
ANGLE_DEG = 35
BONE = "upperarm_f"


def log(*a):
    print(*a, flush=True)


def fresh_copy(src, name):
    obj = src.copy()
    obj.data = src.data.copy()
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    obj.vertex_groups.clear()
    obj.parent = None
    obj.hide_render = True
    return obj


def auto_weight(obj, rig):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")


def evaluated_positions(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = ev.to_mesh()
    out = [(ev.matrix_world @ v.co).copy() for v in m.vertices]
    ev.to_mesh_clear()
    return out


def texture_inventory(obj):
    out = []
    for slot in obj.material_slots:
        mat = slot.material
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    out.append({"image": n.image.name,
                                "size": list(n.image.size),
                                "linked_to": [l.name for l in n.outputs
                                              if l.is_linked][:2]})
    return out


def render_to(obj_to_show, all_meshes, filename):
    for o in all_meshes:
        o.hide_render = o is not obj_to_show
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 768
    scene.render.filepath = str(HERE / filename)
    bpy.ops.render.render(write_still=True)
    log("RENDER", filename, (HERE / filename).stat().st_size, "B")


t0 = time.time()
assert BLEND.is_file(), f"missing {BLEND}"
blend_sha = hashlib.sha256(BLEND.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(BLEND))

src = next(o for o in bpy.context.scene.objects if o.type == "MESH")
rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
log(f"OPEN src={src.name} verts={len(src.data.vertices)} rig={rig.name}")

src_tex = texture_inventory(src)
src_uv = len(src.data.uv_layers)
log("SRC textures", src_tex, "uv_layers", src_uv)

# --- 1. 体素代理壳（只用来算权重，永不渲染）--------------------------------
proxy = fresh_copy(src, "voxel_proxy")
proxy.data.remesh_voxel_size = VOXEL_SIZE
proxy.data.remesh_voxel_adaptivity = 0.0
bpy.ops.object.select_all(action="DESELECT")
proxy.select_set(True)
bpy.context.view_layer.objects.active = proxy
assert bpy.ops.object.voxel_remesh.poll()
bpy.ops.object.voxel_remesh()
log("PROXY verts", len(proxy.data.vertices), "faces", len(proxy.data.polygons))
auto_weight(proxy, rig)
proxy_covered = sum(1 for v in proxy.data.vertices
                    if any(g.weight > 1e-6 for g in v.groups))
log("PROXY auto_weight", proxy_covered, "/", len(proxy.data.vertices))

# --- 2. Data Transfer：把代理壳权重传回原高模 -------------------------------
final = fresh_copy(src, "final_transfer_weights")
for b in rig.data.bones:
    final.vertex_groups.new(name=b.name)
mod = final.modifiers.new("weights_from_voxel_proxy", "DATA_TRANSFER")
mod.object = proxy
mod.use_vert_data = True
mod.data_types_verts = {"VGROUP_WEIGHTS"}
mod.vert_mapping = "POLYINTERP_NEAREST"
mod.layers_vgroup_select_src = "ALL"
mod.layers_vgroup_select_dst = "NAME"
bpy.ops.object.select_all(action="DESELECT")
final.select_set(True)
bpy.context.view_layer.objects.active = final
bpy.ops.object.modifier_apply(modifier=mod.name)
arm_mod = final.modifiers.new("final_armature", "ARMATURE")
arm_mod.object = rig

final_covered = sum(1 for v in final.data.vertices
                    if any(g.weight > 1e-6 for g in v.groups))
log("FINAL transfer_weight", final_covered, "/", len(final.data.vertices),
    "groups", len(final.vertex_groups))

final_tex = texture_inventory(final)
assets_kept = {
    "uv_layers": len(final.data.uv_layers),
    "materials": len(final.data.materials),
    "textures": final_tex,
    "uv_same_as_source": len(final.data.uv_layers) == src_uv,
    "textures_same_as_source": final_tex == src_tex,
}
log("ASSETS_KEPT", assets_kept)

# --- 3. 未变形正面图：证明原 PBR 还在 --------------------------------------
render_to(final, [src, proxy, final], "transfer-rest-front.png")

# --- 4. 同一 35° 驱动下的 A/B 位移与渲图 -----------------------------------
rest_src = evaluated_positions(src)
rest_final = evaluated_positions(final)
pb = rig.pose.bones[BONE]
pb.rotation_mode = "XYZ"
pb.rotation_euler[2] = math.radians(ANGLE_DEG)
bpy.context.view_layer.update()
driven_src = evaluated_positions(src)
driven_final = evaluated_positions(final)


def stats(rest, driven, mode):
    d = [(a - b).length for a, b in zip(rest, driven)]
    moved = sum(1 for x in d if x > 1e-4)
    return {"weight_mode": mode, "vertices": len(d),
            "moved_vertices_gt_0_1mm": moved,
            "moved_ratio": round(moved / len(d), 5),
            "max_displacement_m": round(max(d), 5),
            "mean_displacement_m": round(sum(d) / len(d), 5)}


a = stats(rest_src, driven_src, "nearest-segment rigid 1.0 (11-08 baseline)")
b = stats(rest_final, driven_final, "voxel proxy -> Data Transfer smooth")
log("A_RIGID", a)
log("B_TRANSFER", b)
render_to(src, [src, proxy, final], "transfer-compare-rigid.png")
render_to(final, [src, proxy, final], "transfer-compare-transfer.png")

report = {
    "blender": bpy.app.version_string,
    "source_blend_sha256": blend_sha,
    "voxel_size": VOXEL_SIZE,
    "bone": BONE,
    "angle_deg": ANGLE_DEG,
    "source": {"verts": len(src.data.vertices), "uv_layers": src_uv,
               "textures": src_tex},
    "proxy": {"verts": len(proxy.data.vertices),
              "faces": len(proxy.data.polygons),
              "auto_weight_covered": proxy_covered},
    "transfer": {"verts": len(final.data.vertices),
                 "groups": len(final.vertex_groups),
                 "covered": final_covered,
                 "coverage": round(final_covered / len(final.data.vertices), 5),
                 "assets_kept": assets_kept},
    "deform_a_rigid": a,
    "deform_b_transfer": b,
    "caveat": "覆盖率与位移数字只证明链路可动；变形质量必须看两张同条件图，脚本不评好看、不声称可用",
    "elapsed_seconds": round(time.time() - t0, 2),
}
(HERE / "transfer_probe.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
log("TRANSFER_PROBE_OK", report["elapsed_seconds"], "s")
