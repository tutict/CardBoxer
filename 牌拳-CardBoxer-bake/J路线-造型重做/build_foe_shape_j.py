"""J 路线 P2：壳级「去同源」手术 + 重导带 skin 的 foe GLB。

关键决策（比 A 候选里预估的全链重跑更省，且有实证支撑）：
  * 不增删顶点、不改拓扑、不改材质槽、不改 UV 层数、不改骨架 rest。
  * 权重先按 H 路线 DATA_TRANSFER 回传并 apply；**之后**才对 final 的
    顶点坐标与 UV 做手术。权重数组已固定，改坐标不会再影响
    POLYINTERP_NEAREST 的空间映射。
  * 因此 Voxel 连续壳 / 13 骨绑定 / SURFACE_DEFORM / motion_input_foe
    全都不用重跑，只需重导 GLB + 替换工程资产 + Godot 重新导入。

手术对象（来自 probe_shells_j.py 的区域规则，2,809 壳）：
  SKIRT          长衫下摆  → 缩短 + 收窄成工装围裙，UV 改到暗钢区
  CAPE_OR_PANEL  黑披风    → 收窄 + 缩短成破损背布，UV 改到暗钢区
  HEAD_TOP 小壳  头冠/结晶/红花 → 向头盔中心收拢，UV 改到暗钢区
大壳（头盔本体 / 躯干 / 靴子）一律不动，避免「没头」。

只读 A 路线 .blend；产物全落 J 目录，不回写任何归档、不动游戏工程。
用法：blender.exe -b --python build_foe_shape_j.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "A路线-资产重做" / "对手怪-可变形连续壳.blend"
OUT_GLB = HERE / "foe-rigged-v2.glb"
OUT_JSON = HERE / "data" / "build_shape_j.json"

UV_PATCH = (0.10, 0.88)     # foe 贴图左上均匀深灰区（v=1 为图像顶）
UV_SPAN = 0.018
SKIRT_Z, SKIRT_SQUEEZE, SKIRT_NARROW = 0.95, 0.45, 0.72
CAPE_Z, CAPE_SQUEEZE, CAPE_NARROW, CAPE_FLATTEN = 0.85, 0.50, 0.55, 0.60
HEAD_SMALL_SHELL_MAX = 200
HEAD_PULL_X, HEAD_DROP_Z = 0.45, 0.12


def log(*a):
    print(*a, flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def textures(obj) -> list[dict]:
    out = []
    for slot in obj.material_slots:
        mat = slot.material
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    out.append({"image": n.image.name,
                                "size": list(n.image.size)})
    return sorted(out, key=lambda d: d["image"])


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


def classify(c, lo, hi) -> str:
    cx, cy, cz = c
    zx, zy, zz = (hi[i] - lo[i] for i in range(3))
    if cz > 1.48:
        return "HEAD_TOP"
    if cz > 1.30:
        return "HEAD"
    if zz > 0.55 and (zy > 0.35 or zx > 0.55) and cz < 1.35:
        return "CAPE_OR_PANEL"
    if cz < 0.95 and zz > 0.25 and abs(cx) < 0.40:
        return "SKIRT"
    if cz < 0.42:
        return "BOOTS"
    return "BODY"


def shell_map(mesh) -> dict[int, dict]:
    """按面连通分组；返回 root -> {verts, region, ...}。"""
    nv = len(mesh.vertices)
    parent = list(range(nv))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for p in mesh.polygons:
        vs = p.vertices
        for v in vs[1:]:
            union(vs[0], v)
    groups = defaultdict(list)
    co = [tuple(v.co) for v in mesh.vertices]
    for v in mesh.vertices:
        groups[find(v.index)].append(v.index)
    out = {}
    for root, ids in groups.items():
        xs = [co[i][0] for i in ids]
        ys = [co[i][1] for i in ids]
        zs = [co[i][2] for i in ids]
        lo = [min(xs), min(ys), min(zs)]
        hi = [max(xs), max(ys), max(zs)]
        c = [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]
        out[root] = {"ids": ids, "verts": len(ids),
                     "region": classify(c, lo, hi),
                     "centroid": c}
    return out, find


def patch_uv_sample(image) -> list[float]:
    """读回 UV patch 区域的线性均值，证明目标色块确实是暗钢区。"""
    w, h = image.size
    acc = [0.0, 0.0, 0.0]
    n = 0
    for i in range(8):
        for k in range(8):
            u = UV_PATCH[0] + UV_SPAN * (i + 0.5) / 8.0
            v = UV_PATCH[1] + UV_SPAN * (k + 0.5) / 8.0
            x = min(w - 1, int(u * w))
            y = min(h - 1, int((1.0 - v) * h))
            idx = (y * w + x) * 4
            for c in range(3):
                acc[c] += image.pixels[idx + c]
            n += 1
    return [round(a / n, 4) for a in acc]


def main() -> int:
    assert BLEND.is_file(), BLEND
    blend_sha = sha256(BLEND)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene

    src = next(o for o in scene.objects
               if o.type == "MESH"
               and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))
    shell = next(m for m in src.modifiers
                 if m.type == "SURFACE_DEFORM").target
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    bone_names = [b.name for b in rig.data.bones]
    shell_groups = [g.name for g in shell.vertex_groups]
    assert set(bone_names) == set(shell_groups)
    src_uv = len(src.data.uv_layers)
    src_tex = textures(src)

    # ── 1. 权重先回传并 apply（此时坐标仍是 H 原样）────────────
    final = fresh_copy(src, "foe_HI_skinned_V2")
    for name in bone_names:
        final.vertex_groups.new(name=name)
    mod = final.modifiers.new("weights_from_continuous_shell",
                              "DATA_TRANSFER")
    mod.object = shell
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    mod.layers_vgroup_select_src = "ALL"
    mod.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.select_all(action="DESELECT")
    final.select_set(True)
    bpy.context.view_layer.objects.active = final
    bpy.ops.object.modifier_apply(modifier=mod.name)
    covered_before = sum(1 for v in final.data.vertices
                         if any(g.weight > 1e-6 for g in v.groups))
    total = len(final.data.vertices)

    # ── 2. 顶点 / UV 手术（权重已固定，改坐标不再影响映射）──────
    groups, find = shell_map(final.data)
    targets: dict[str, list[int]] = defaultdict(list)
    for root, info in groups.items():
        reg = info["region"]
        if reg in ("SKIRT", "CAPE_OR_PANEL"):
            targets[reg].extend(info["ids"])
        elif (reg == "HEAD_TOP"
              and info["verts"] <= HEAD_SMALL_SHELL_MAX
              and info["centroid"][2] > 1.50):
            targets["HEAD_ORNAMENT"].extend(info["ids"])
    target_ids = set()
    for ids in targets.values():
        target_ids.update(ids)

    moved = 0
    for v in final.data.vertices:
        if v.index not in target_ids:
            continue
        root = find(v.index)
        reg = groups[root]["region"]
        x, y, z = v.co
        if reg == "SKIRT":
            v.co = (x * SKIRT_NARROW, y,
                    SKIRT_Z + (z - SKIRT_Z) * SKIRT_SQUEEZE)
        elif reg == "CAPE_OR_PANEL":
            v.co = (x * CAPE_NARROW, y * CAPE_FLATTEN,
                    CAPE_Z + (z - CAPE_Z) * CAPE_SQUEEZE)
        elif reg == "HEAD_TOP":
            v.co = (x * HEAD_PULL_X, y, z - HEAD_DROP_Z)
        moved += 1

    uv_layer = final.data.uv_layers.active
    assert uv_layer is not None, "no UV layer"
    uv_fixed = 0
    for p in final.data.polygons:
        if p.vertices[0] not in target_ids:
            continue
        for li in p.loop_indices:
            uv_layer.data[li].uv = (
                UV_PATCH[0] + UV_SPAN * 0.5,
                UV_PATCH[1] + UV_SPAN * 0.5)
            uv_fixed += 1

    # ── 3. 校验：结构一件没变 ──────────────────────────────────
    covered_after = sum(1 for v in final.data.vertices
                        if any(g.weight > 1e-6 for g in v.groups))
    arm_mod = final.modifiers.new("foe_rig", "ARMATURE")
    arm_mod.object = rig
    assets = {"uv_layers": len(final.data.uv_layers),
              "materials": len(final.data.materials),
              "textures": textures(final),
              "uv_same": len(final.data.uv_layers) == src_uv,
              "textures_same": textures(final) == src_tex}
    assert assets["uv_same"] and assets["textures_same"]
    # A 路线记录的就是 64,006/64,024 = 99.9719%（18 个顶点在代理壳
    # 外拿不到权重），不是 100%。关键 invariants 是「手术前后覆盖数
    # 逐字节相同」与「覆盖 > 99%」，不是覆盖到每一个顶点。
    assert covered_before == covered_after, \
        (covered_before, covered_after)
    assert covered_before > 0.99 * total, (covered_before, total)
    assert len(final.data.vertices) == len(src.data.vertices) == total
    assert len(final.data.polygons) == len(src.data.polygons)

    base_img = next(n.image for n in
                    final.material_slots[0].material.node_tree.nodes
                    if n.type == "TEX_IMAGE" and n.image
                    and "normal" not in n.image.name.lower()
                    and "roughness" not in n.image.name.lower())
    patch_rgb = patch_uv_sample(base_img)
    assert max(patch_rgb) < 0.35, patch_rgb

    # ── 4. 导出 ────────────────────────────────────────────────
    bpy.ops.object.select_all(action="DESELECT")
    final.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = final
    result = bpy.ops.export_scene.gltf(
        filepath=str(OUT_GLB), export_format="GLB",
        use_selection=True, export_apply=False,
        export_skins=True, export_animations=False,
        export_materials="EXPORT", export_yup=True,
        export_cameras=False, export_lights=False)
    assert list(result) == ["FINISHED"]
    assert OUT_GLB.is_file() and OUT_GLB.stat().st_size > 1_000_000

    report = {
        "blender": bpy.app.version_string,
        "source_blend": str(BLEND), "source_blend_sha256": blend_sha,
        "source": {"object": src.name, "verts": len(src.data.vertices),
                   "polygons": len(src.data.polygons),
                   "uv_layers": src_uv, "textures": src_tex},
        "rig": {"bones": bone_names},
        "shells": len(groups),
        "surgery": {
            "params": {
                "SKIRT": [SKIRT_Z, SKIRT_SQUEEZE, SKIRT_NARROW],
                "CAPE": [CAPE_Z, CAPE_SQUEEZE, CAPE_NARROW,
                         CAPE_FLATTEN],
                "HEAD": [HEAD_SMALL_SHELL_MAX, HEAD_PULL_X,
                         HEAD_DROP_Z],
                "uv_patch": list(UV_PATCH), "uv_span": UV_SPAN},
            "target_verts": {k: len(v) for k, v in targets.items()},
            "moved_verts": moved, "uv_loops_rewritten": uv_fixed,
            "uv_patch_linear_rgb": patch_rgb},
        "integrity": {
            "verts_before": total, "verts_after": len(final.data.vertices),
            "polygons_before": len(src.data.polygons),
            "polygons_after": len(final.data.polygons),
            "uv_layers": assets["uv_layers"],
            "materials": assets["materials"],
            "textures_same": assets["textures_same"],
            "weighted_before": covered_before,
            "weighted_after": covered_after},
        "export": {"file": OUT_GLB.name,
                   "bytes": OUT_GLB.stat().st_size,
                   "sha256": sha256(OUT_GLB),
                   "export_apply": False, "export_skins": True},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    log("SURGERY", report["surgery"]["target_verts"],
        "moved", moved, "uv_loops", uv_fixed)
    log("INTEGRITY", report["integrity"])
    log("EXPORT", OUT_GLB.stat().st_size, "B", sha256(OUT_GLB)[:16])
    log("FOE_SHAPE_J_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
