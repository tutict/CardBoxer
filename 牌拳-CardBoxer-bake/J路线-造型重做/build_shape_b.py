"""B 路线 P1：按 P0 钉死的 195 个壳 ID 做精确删壳，重导带 skin 的 GLB。

与 r1（build_foe_shape_j.py）唯一的本质差别：
  r1  对目标壳做轴向压缩 → 薄壳被拉成针状面，反而撕碎披风；
  本版 把目标壳所有顶点塌缩到**该壳自身质心**（+1e-5 确定性微抖动，
        保住法线可算），面退化成零面积 ⇒ 渲染不可见且不产生尖刺。

结构 invariants 全守恒（顶点/面/UV 层/材质槽/贴图/权重覆盖逐项不变），
所以不必重跑 Voxel 连续壳 / 13 骨绑定 / SURFACE_DEFORM / rest 重建，
只需重导 GLB + 替换工程资产 + Godot 重新导入。

只读 A 路线 .blend；产物全落 J 目录，不回写任何归档、不改游戏工程。
用法：blender.exe -b --python build_shape_b.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "A路线-资产重做" / "对手怪-可变形连续壳.blend"
TARGETS = HERE / "data" / "shell_targets_b.json"
EXTRA = HERE / "data" / "extra_targets_b.json"   # 第二轮补删（青冠 / 青云纹）
OUT_GLB = HERE / "foe-rigged-b.glb"
OUT_JSON = HERE / "data" / "build_shape_b.json"
SHOTS = HERE / "shots" / "after_b"

JITTER = 1e-5
VIEWS = {
    "front": ((0.0, -4.0, 0.95), (math.pi / 2, 0.0, 0.0)),
    "back": ((0.0, 4.0, 0.95), (math.pi / 2, 0.0, math.pi)),
    "side": ((4.0, 0.0, 0.95), (math.pi / 2, 0.0, math.pi / 2)),
    "angle45": ((2.8, -2.8, 0.95), (math.pi / 2, 0.0, math.pi / 4)),
}


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


def shell_roots(mesh):
    """与 P0 完全相同的 union-find（顶点序 / 面序遍历序一致 ⇒ root 一致）。"""
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
    roots = [find(v.index) for v in mesh.vertices]
    groups = defaultdict(list)
    for v in mesh.vertices:
        groups[find(v.index)].append(v.index)
    return roots, groups


def render_preview(scene, final, roots, target_set):
    """在独立副本上按「目标/保留」二色渲 4 视角，不改 final 的材质槽。"""
    SHOTS.mkdir(parents=True, exist_ok=True)
    prev = final.copy()
    prev.data = final.data.copy()
    scene.collection.objects.link(prev)
    prev.name = "B_PREVIEW"
    prev.hide_render = False
    # 订正：只隐藏 MESH 不够。.blend 里的 CURVE / FONT / SURFACE 等
    # 非 MESH 可渲染对象也会进 Workbench，侧视图那条细线可能来自它们。
    # 除相机/灯/空对象外一律隐藏，并把被隐藏对象类型写进报告。
    hidden_types = []
    for o in scene.objects:
        if o is prev or o.type in ("CAMERA", "LIGHT", "EMPTY"):
            continue
        o.hide_render = True
        hidden_types.append({"name": o.name, "type": o.type})

    pm = prev.data
    pm.materials.clear()
    for name, rgba in (("B_TARGET", (0.05, 0.95, 0.15, 1.0)),
                       ("B_KEEP", (0.62, 0.62, 0.62, 1.0))):
        m = bpy.data.materials.new(name)
        m.diffuse_color = rgba
        pm.materials.append(m)
    for p in pm.polygons:
        p.material_index = 0 if roots[p.vertices[0]] in target_set else 1

    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.render.film_transparent = True
    scene.render.resolution_x = 640
    scene.render.resolution_y = 768
    cam_data = bpy.data.cameras.new("B_AFTER_CAM")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.1
    cam = bpy.data.objects.new("B_AFTER_CAM", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    written = []
    for vname, (loc, rot) in VIEWS.items():
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = str(SHOTS / f"b-after-{vname}.png")
        bpy.ops.render.render(write_still=True)
        written.append(SHOTS / f"b-after-{vname}.png")
    # 预览对象不再参与导出
    prev.hide_render = True
    return written, hidden_types


def main() -> int:
    assert BLEND.is_file(), BLEND
    assert TARGETS.is_file() and EXTRA.is_file()
    spec = json.loads(TARGETS.read_text(encoding="utf-8"))
    extra = json.loads(EXTRA.read_text(encoding="utf-8"))
    assert spec["ok"] and not spec["failed"], "P0 规则未验收"
    assert extra["ok"] and not extra["failed"], "第二轮补删规则未验收"
    round1 = set(spec["target_shell_ids"])
    extra_set = set(extra["extra_ids"])
    assert not (round1 & extra_set), "两轮目标集重叠"
    target_set = round1 | extra_set
    assert len(target_set) == (len(round1) + len(extra_set))

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
    assert set(bone_names) == set(g.name for g in shell.vertex_groups)
    src_uv = len(src.data.uv_layers)
    src_tex = textures(src)

    # ── 1. 权重回传（坐标仍为原样，与 H / r1 同链）──────────────
    final = fresh_copy(src, "foe_HI_skinned_B")
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

    # ── 2. 分壳并对账 P0 的壳 ID ───────────────────────────────
    roots, groups = shell_roots(final.data)
    assert len(groups) == 2809, len(groups)
    assert target_set <= set(groups), "P0 目标壳 ID 在本次分壳中失配"
    co0 = [tuple(v.co) for v in final.data.vertices]
    target_verts = [vi for vi, r in enumerate(roots) if r in target_set]

    # ── 3. 塌缩到各自壳质心（不是轴向压缩）────────────────────
    centroids = {}
    for r in target_set:
        ids = groups[r]
        c = [sum(co0[i][k] for i in ids) / len(ids) for k in range(3)]
        centroids[r] = c
    for n, vi in enumerate(target_verts):
        r = roots[vi]
        cx, cy, cz = centroids[r]
        ang = n * 2.399963229728653  # 黄金角，确定性微抖动
        final.data.vertices[vi].co = (
            cx + JITTER * math.cos(ang),
            cy + JITTER * math.sin(ang),
            cz + JITTER * math.sin(ang * 1.7))
    final.data.update()

    # ── 3b. 统一目标壳权重（round2 关键修复）────────────────────
    # 塌缩后的顶点仍带着各自原来的骨骼权重。引擎内一旦驱动，不同权重
    # 会把「聚成一个点」的顶点拉向不同方向，零面积面重新展开成细长
    # 碎片 —— round1 的 j-sv-foe.png 里那串虚线状碎片就是这么来的。
    # 统一给 hips 1.0，让整个目标壳作为刚体随同一根骨移动。
    # vertex_groups 挂在 Object 上，不在 Mesh datablock 上。
    for vg in list(final.vertex_groups):
        vg.remove(target_verts)
    hips_group = final.vertex_groups.get("hips")
    assert hips_group is not None, "rig 里没有 hips 骨"
    hips_group.add(target_verts, 1.0, "REPLACE")
    targets_unified = all(
        len(final.data.vertices[vi].groups) == 1
        and abs(final.data.vertices[vi].groups[0].weight - 1.0) < 1e-5
        and final.data.vertices[vi].groups[0].group
        == hips_group.index
        for vi in target_verts)

    # ── 4. invariants：非目标顶点逐值不变，结构一件没动 ─────────
    co1 = [tuple(v.co) for v in final.data.vertices]
    non_target_unchanged = all(
        co0[vi] == co1[vi] for vi in range(total)
        if roots[vi] not in target_set)
    max_jitter = max(
        math.dist(co1[vi], centroids[roots[vi]]) for vi in target_verts)
    covered_after = sum(1 for v in final.data.vertices
                        if any(g.weight > 1e-6 for g in v.groups))
    assets = {"uv_layers": len(final.data.uv_layers),
              "materials": len(final.data.materials),
              "textures": textures(final),
              "uv_same": len(final.data.uv_layers) == src_uv,
              "textures_same": textures(final) == src_tex}
    integrity = {
        "verts_before": len(src.data.vertices), "verts_after": total,
        "polygons_before": len(src.data.polygons),
        "polygons_after": len(final.data.polygons),
        "uv_layers": assets["uv_layers"],
        "materials": assets["materials"],
        "textures_same": assets["textures_same"],
        "weighted_before": covered_before,
        "weighted_after": covered_after,
        "targets_all_hips_weight_1": targets_unified,
        "non_target_vertices_bytewise_unchanged": non_target_unchanged,
        "target_verts_collapsed": len(target_verts),
        "max_distance_to_centroid": round(max_jitter, 9),
    }
    assert total == len(src.data.vertices)
    assert len(final.data.polygons) == len(src.data.polygons)
    assert assets["uv_same"] and assets["textures_same"]
    # 统一权重可能让原本拿不到权重的少数孤立顶点变成有覆盖，
    # 所以判据是「不减少」，不是「逐字节相同」。
    assert covered_after >= covered_before
    assert covered_after > 0.99 * total
    assert non_target_unchanged
    assert targets_unified
    assert max_jitter <= 2 * JITTER, max_jitter

    # ── 5. 删后预览（先证伪「头顶会不会露洞」）─────────────────
    written, hidden_types = render_preview(scene, final, roots,
                                           target_set)

    # ── 6. 导出带 skin 的 GLB ──────────────────────────────────
    arm_mod = final.modifiers.new("foe_rig", "ARMATURE")
    arm_mod.object = rig
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

    checks = {
        "p0_targets_verified": spec["ok"] and not spec["failed"],
        "extra_targets_verified": extra["ok"] and not extra["failed"],
        "round_sets_disjoint": not (round1 & extra_set),
        "shell_ids_match_p0": target_set <= set(groups),
        "shell_count_2809": len(groups) == 2809,
        "verts_conserved": integrity["verts_before"]
                           == integrity["verts_after"],
        "polygons_conserved": integrity["polygons_before"]
                              == integrity["polygons_after"],
        "uv_and_textures_conserved": assets["uv_same"]
                                     and assets["textures_same"],
        "weights_not_reduced": covered_after >= covered_before,
        "targets_all_single_bone": targets_unified,
        "non_target_unchanged": non_target_unchanged,
        "targets_collapsed_tightly": max_jitter <= 2 * JITTER,
        "target_verts_match_combined": (
            len(target_verts)
            == spec["totals"]["verts"] + extra["counts"]["verts"]),
        "preview_shots_written": all(
            p.is_file() and p.stat().st_size > 2000 for p in written),
        "glb_exported": OUT_GLB.stat().st_size > 1_000_000,
    }
    report = {
        "blender": bpy.app.version_string,
        "source_blend": str(BLEND), "source_blend_sha256": blend_sha,
        "target_spec": str(TARGETS),
        "target_spec_sha256": sha256(TARGETS),
        "extra_spec": str(EXTRA),
        "extra_spec_sha256": sha256(EXTRA),
        "method": spec["surgery_method"],
        "weight_fix": (
            "目标壳权重统一为 hips=1.0，避免驱动时不同骨骼把塌缩点撕开"),
        "jitter": JITTER,
        "rig": {"bones": bone_names},
        "targets": {
            "shells": len(target_set), "verts": len(target_verts),
            "verts_ratio": round(len(target_verts) / total, 6),
            "round1_shells": len(round1), "extra_shells": len(extra_set),
            "round1_verts": spec["totals"]["verts"],
            "extra_verts": extra["counts"]["verts"],
            "by_group": {g: v["verts"] for g, v in
                         spec["target_groups"].items()},
        },
        "integrity": integrity,
        "preview_shots": [str(p) for p in written],
        "hidden_for_preview": hidden_types,
        "export": {"file": OUT_GLB.name, "bytes": OUT_GLB.stat().st_size,
                   "sha256": sha256(OUT_GLB),
                   "export_apply": False, "export_skins": True},
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    report["ok"] = not report["failed"]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    log("TARGETS", report["targets"])
    log("INTEGRITY", integrity)
    log("PREVIEW", len(written), "shots")
    log("EXPORT", OUT_GLB.stat().st_size, "B", sha256(OUT_GLB)[:16])
    for k, v in checks.items():
        log("CHECK", k, v)
    log("BUILD_SHAPE_B_OK" if report["ok"] else "BUILD_SHAPE_B_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
