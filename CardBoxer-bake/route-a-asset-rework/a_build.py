"""A 路线主链：把「只能算权重的 Voxel 代理」做成可交付的可变形资产。

产物：
  1. foe-deformable-continuous-shell.blend —— 打开即可驱动：
     · A-pose rest 13 骨 rig
     · 三角化的 Voxel 连续壳（3 壳）+ ARMATURE_AUTO 平滑权重
     · 原高模 2,809 壳 / 1 层 UV / 3 张 4096² PBR 一张不动，
       通过 SURFACE_DEFORM 跟随连续壳，bind 数据随 .blend 保存
     · 3 张 PBR 已 packed，不依赖外部文件路径
  2. a_build.json —— 全 72 帧 × 两组增益的变形质量门禁，
     逐帧与 route-c-deformation-v2/c2_build.json 的 V1_base / V1_gain 同帧对照
  3. frames/ —— 定稿代表帧 + 55° 侧视 + A2 x1.0/x1.5 单变量对照

只读源 .blend 与 V2 归档，不回写，不改游戏源码，不进 Godot。
用法：blender.exe -b --python a_build.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # 别刷新已归档目录里的 __pycache__

import copy
import hashlib
import json
import time
from pathlib import Path

import bmesh
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "route-c-deformation-v2"))
sys.path.insert(0, str(BAKE / "route-c-real-3d-fix"))
import c2_build as C2  # noqa: E402
import c_build as C  # noqa: E402

BLEND = BAKE / "foe-blender-modeling-v1" / "foe-V1.blend"
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3d-attack-gifs" / "apose_joints.json"
MAPPING = BAKE / "3d-attack-gifs" / "puppet_mapping.json"
V2_REPORT = BAKE / "route-c-deformation-v2" / "c2_build.json"
OUT_BLEND = HERE / "foe-deformable-continuous-shell.blend"
VOXEL = 0.020
ARM_GAIN = 1.5
CARDS = (("jab", 14), ("cross", 22), ("wave", 36))
KEY_SHOTS = [
    ("stance", None, 0, 0.0), ("jab01", "jab", 0, 0.0),
    ("jab07", "jab", 6, 0.0), ("jab13", "jab", 12, 0.0),
    ("cross01", "cross", 0, 0.0), ("cross11", "cross", 10, 0.0),
    ("cross21", "cross", 20, 0.0), ("wave01", "wave", 0, 0.0),
    ("wave18", "wave", 17, 0.0), ("wave35", "wave", 34, 0.0),
]
HIT_SHOTS = (("jab07", "jab", 6), ("cross11", "cross", 10),
             ("wave18", "wave", 17))


def log(*a):
    print(*a, flush=True)


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


def build_chain():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    stance = C.joints_of(table, None, 0)
    P = C.apose_points(spec)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    for o in list(scene.objects):
        if o.type == "ARMATURE":
            bpy.data.objects.remove(o, do_unlink=True)
    for m in list(src.modifiers):
        src.modifiers.remove(m)
    src.hide_render = False
    src_uv = len(src.data.uv_layers)
    src_tex = C.texture_inventory(src)
    src_shells = shell_count(src.data)

    arm_data = bpy.data.armatures.new("a_apose_rig")
    rig = bpy.data.objects.new("a_apose_rig", arm_data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for name, parent, u, v in C.CHAIN:
        eb = arm_data.edit_bones.new(name)
        hx, hz = P[u]
        tx, tz = P[v]
        eb.head, eb.tail = (hx, 0.0, hz), (tx, 0.0, tz)
        if parent:
            eb.parent = made[parent]
        made[name] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.bone.inherit_scale = "NONE"
    bpy.context.view_layer.update()

    shell = C.fresh_copy(src, "a_continuous_shell")
    shell.data.remesh_voxel_size = VOXEL
    shell.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    assert bpy.ops.object.voxel_remesh.poll()
    bpy.ops.object.voxel_remesh()
    # Surface Deform 要求 target 全凸多边形；Voxel quad 常不共面，
    # 不三角化会报 "Target contains concave polygons" 且 bind 失败。
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.to_mesh(shell.data)
    bm.free()
    shell.data.update()
    tri_ratio = sum(1 for f in shell.data.polygons if len(f.vertices) == 3) \
        / len(shell.data.polygons)
    C.auto_weight(shell, rig)
    shell_covered = sum(1 for v in shell.data.vertices
                        if any(g.weight > 1e-6 for g in v.groups))

    bpy.ops.object.select_all(action="DESELECT")
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    sd = src.modifiers.new("follow_continuous_shell", "SURFACE_DEFORM")
    sd.target = shell
    assert bpy.ops.object.surfacedeform_bind.poll()
    bpy.ops.object.surfacedeform_bind(modifier=sd.name)
    assert bool(getattr(sd, "is_bound", False)), "Surface Deform bind failed"

    C.setup_camera(scene, 0.0)
    rest_pos, rest_edges = C.evaluated(src)
    raw = [src.matrix_world @ v.co for v in src.data.vertices]
    bind_drift = max((a - b).length for a, b in zip(rest_pos, raw))
    hf, hb, foot = C2.clusters(rest_pos, P)
    info = {
        "src": {"verts": len(src.data.vertices), "shells": src_shells,
                "uv": src_uv, "textures": len(src_tex)},
        "shell": {"verts": len(shell.data.vertices),
                  "faces": len(shell.data.polygons),
                  "shells": shell_count(shell.data),
                  "tri_ratio": round(tri_ratio, 5),
                  "auto_weight_covered": shell_covered},
        "bind": {"is_bound": True, "rest_drift_m": round(bind_drift, 8)},
        "assets": {"uv_layers": len(src.data.uv_layers),
                   "materials": len(src.data.materials),
                   "textures": C.texture_inventory(src),
                   "uv_same": len(src.data.uv_layers) == src_uv,
                   "textures_same": C.texture_inventory(src) == src_tex},
    }
    log("CHAIN " + json.dumps(info, ensure_ascii=False))
    return dict(scene=scene, src=src, shell=shell, rig=rig, P=P, table=table,
                stance=stance, rest_pos=rest_pos, rest_edges=rest_edges,
                hf=hf, hb=hb, foot=foot, hip_z=P["hip"][1],
                sh_z=P["shoulder"][1], info=info)


def render(ch, name, deg=0.0):
    scene, src, shell = ch["scene"], ch["src"], ch["shell"]
    C.setup_camera(scene, deg)
    src.hide_render = False
    shell.hide_render = True
    p = HERE / "frames" / f"{name}.png"
    scene.render.filepath = str(p)
    bpy.ops.render.render(write_still=True)
    b = p.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 10000
    return {"file": p.name, "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest()}


def main() -> int:
    t0 = time.time()
    base_mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    gain_mapping = copy.deepcopy(base_mapping)
    gain_mapping["arm_gain_deg"] = {
        k: v * ARM_GAIN for k, v in base_mapping["arm_gain_deg"].items()}
    v2 = json.loads(V2_REPORT.read_text(encoding="utf-8"))
    v2_by_key = {(r["card"], r["frame"]): r for r in v2["all_frames"]["rows"]}
    ch = build_chain()

    def metrics(card, frame, mapping):
        C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                     card, frame, mapping)
        pos, _ = C.evaluated(ch["src"])
        return C2.frame_metrics(ch["rest_pos"], ch["rest_edges"], pos,
                                ch["hf"], ch["hb"], ch["foot"],
                                ch["hip_z"], ch["sh_z"])

    # --- 全 72 帧 × 两组增益，逐帧与 V2 同帧对照 ---------------------------
    rows = []
    for cid, n in CARDS:
        for f in range(n):
            m_x1 = metrics(cid, f, base_mapping)
            m_x15 = metrics(cid, f, gain_mapping)
            ref = v2_by_key[(cid, f)]
            rows.append({
                "card": cid, "frame": f,
                "A2_x1": m_x1, "A2_x15": m_x15,
                "V2_V1_base": {k: ref["V1_base"][k] for k in m_x1},
                "V2_V1_gain": {k: ref["V1_gain"][k] for k in m_x1},
            })
        log(f"METRICS {cid} {n} frames elapsed={time.time()-t0:.1f}s")
    log(f"ALL_FRAMES rows={len(rows)}")

    # --- 代表帧渲染 --------------------------------------------------------
    shots = []
    for name, card, frame, _deg in KEY_SHOTS:
        C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                     card, frame, gain_mapping)
        png = render(ch, f"a-{name}-x15")
        png.update({"shot": name, "card": card, "frame": frame, "tag": "A2_x15"})
        shots.append(png)
    for name, card, frame in HIT_SHOTS:
        C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                     card, frame, base_mapping)
        png = render(ch, f"a-{name}-x1")
        png.update({"shot": name, "card": card, "frame": frame, "tag": "A2_x1"})
        shots.append(png)
    # 侧视必须显式回到站架，否则沿用上面循环最后一帧的 pose。
    C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                 None, 0, gain_mapping)
    side = render(ch, "a-stance-angle55", 55.0)
    side.update({"shot": "stance-angle55", "card": None, "frame": 0,
                 "tag": "A2_x15", "angle_deg": 55.0})
    shots.append(side)
    log(f"SHOTS={len(shots)}")

    # --- 导出可交付 .blend --------------------------------------------------
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND), compress=True)
    blend_bytes = OUT_BLEND.read_bytes()
    export = {"file": OUT_BLEND.name, "bytes": len(blend_bytes),
              "sha256": hashlib.sha256(blend_bytes).hexdigest()}

    # 重开验证：bind 数据 / 骨架 / 打包贴图是否真的随文件走
    bpy.ops.wm.open_mainfile(filepath=str(OUT_BLEND))
    reopen = {}
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    hi = next(o for o in meshes if any(m.type == "SURFACE_DEFORM"
                                       for m in o.modifiers))
    sd = next(m for m in hi.modifiers if m.type == "SURFACE_DEFORM")
    rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    imgs = [im for im in bpy.data.images
            if im.source == "FILE" and tuple(im.size) == (4096, 4096)]
    reopen = {
        "surface_deform_is_bound": bool(getattr(sd, "is_bound", False)),
        "surface_deform_target": sd.target.name if sd.target else None,
        "rig_count": len(rigs),
        "rig_bones": len(rigs[0].pose.bones) if rigs else 0,
        "high_poly_verts": len(hi.data.vertices),
        "high_poly_uv_layers": len(hi.data.uv_layers),
        "packed_4096_textures": sum(1 for im in imgs if im.packed_file),
        "textures_4096": len(imgs),
    }
    # 重开后真的驱动一帧，证明不是「存了个不能动的壳」
    scene2 = bpy.context.scene
    rig2 = rigs[0]
    P = ch["P"]
    table, stance = ch["table"], ch["stance"]
    rest2, _ = C.evaluated(hi)
    C.pose_frame(rig2, P, table, stance, "cross", 10, gain_mapping)
    posed2, _ = C.evaluated(hi)
    reopen["reopen_drive_max_displacement_m"] = round(
        max((a - b).length for a, b in zip(rest2, posed2)), 5)
    log("REOPEN " + json.dumps(reopen, ensure_ascii=False))

    report = {
        "blender": bpy.app.version_string,
        "fingerprints": {k: hashlib.sha256(p.read_bytes()).hexdigest()
                         for k, p in (("blend", BLEND), ("table", TABLE),
                                      ("spec", SPEC), ("mapping", MAPPING),
                                      ("v2_report", V2_REPORT))},
        "method": "Voxel continuous shell (triangulated) + ARMATURE_AUTO "
                  "+ SURFACE_DEFORM bind; original high-poly keeps its "
                  "2,809 shells / UV / 3 packed 4096 PBR textures",
        "params": {"voxel_size": VOXEL, "arm_only_gain": ARM_GAIN},
        "chain": ch["info"],
        "export": export,
        "reopen": reopen,
        "all_frames": {"count": len(rows), "cards": {k: n for k, n in CARDS},
                       "rows": rows},
        "shots": shots,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    (HERE / "a_build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    log(f"A_BUILD_OK frames={len(rows)} shots={len(shots)} "
        f"blend_bytes={export['bytes']} elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
