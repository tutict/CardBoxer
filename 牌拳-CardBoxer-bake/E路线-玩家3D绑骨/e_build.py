"""E 路线主链：给玩家 V4b 复刻 A 路线的「可变形连续壳」资产。

与 A 路线（对手怪）完全相同的链：
  A-pose rest 13 骨 → Voxel 连续壳(三角化) → ARMATURE_AUTO 平滑权重
  → 原高模 SURFACE_DEFORM bind → 相对 rest 的增量逐帧驱动。
三处专属差异：
  1. 源是 probe_v4b_source.py 产出的「玩家V4b-源.blend」（GLB 已归一化
     到 1.72 m、3 张 4096² PBR 已 packed、场景自带相机与灯）；
  2. A-pose 点表用 apose_joints.json["player"]，不是 ["foe"]；
  3. 网格 57,901 顶点 / 2,035 壳，且多了长发、长衫下摆、披肩、流苏等
     悬垂薄件 —— Voxel 会溶掉多少、SURFACE_DEFORM 还能不能 bind，
     由本脚本的探针与全帧质量度量实测，不预设结论。

复用而非复制：C.apose_points 只按 spec["foe"] 取表，把 player 的表喂成
{"foe": ...} 即可零复制地拿到同一套 0.26/0.60/0.58/0.04 换算公式。

用法：
  blender.exe -b --python e_build.py -- --probe   # 小样本看图
  blender.exe -b --python e_build.py              # 全 72 帧 + 交付 .blend
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import bmesh
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "C路线-变形质量V2"))
sys.path.insert(0, str(BAKE / "C路线-真3D修复"))
sys.path.insert(0, str(BAKE / "A路线-资产重做"))
import a_build as A  # noqa: E402  - shell_count 唯一真相
import c2_build as C2  # noqa: E402  - clusters / frame_metrics
import c_build as C  # noqa: E402  - 整条驱动链

BLEND = HERE / "玩家V4b-源.blend"
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3D攻击GIF" / "apose_joints.json"
MAPPING = BAKE / "3D攻击GIF" / "puppet_mapping.json"
A_REPORT = BAKE / "A路线-资产重做" / "a_build.json"
OUT_BLEND = HERE / "玩家V4b-可变形连续壳.blend"
OUT_JSON = HERE / "e_build.json"
PROBE_JSON = HERE / "e_probe.json"

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
PROBE_SHOTS = [
    ("stance", None, 0, 0.0), ("jab07", "jab", 6, 0.0),
    ("cross11", "cross", 10, 0.0), ("wave18", "wave", 17, 0.0),
]


def log(*a):
    print(*a, flush=True)


def player_apose_points(spec):
    """零复制复用 C.apose_points：它只按 spec["foe"] 取表。"""
    return C.apose_points({"foe": spec["player"]})


def build_chain():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    stance = C.joints_of(table, None, 0)
    P = player_apose_points(spec)
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
    src_shells = A.shell_count(src.data)

    arm_data = bpy.data.armatures.new("e_apose_rig")
    rig = bpy.data.objects.new("e_apose_rig", arm_data)
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
        assert (eb.tail - eb.head).length > 1e-4, f"zero-length bone {name}"
        if parent:
            eb.parent = made[parent]
        made[name] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.bone.inherit_scale = "NONE"
    bpy.context.view_layer.update()
    log(f"APOSE_RIG_PLAYER bones={len(rig.pose.bones)} "
        f"head_z={P['head'][1]:.4f} hip_z={P['hip'][1]:.4f}")

    shell = C.fresh_copy(src, "e_continuous_shell")
    shell.data.remesh_voxel_size = VOXEL
    shell.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    assert bpy.ops.object.voxel_remesh.poll()
    bpy.ops.object.voxel_remesh()
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
                  "shells": A.shell_count(shell.data),
                  "tri_ratio": round(tri_ratio, 5),
                  "auto_weight_covered": shell_covered},
        "bind": {"is_bound": True, "rest_drift_m": round(bind_drift, 8)},
        "assets": {"uv_layers": len(src.data.uv_layers),
                   "materials": len(src.data.materials),
                   "textures": C.texture_inventory(src),
                   "uv_same": len(src.data.uv_layers) == src_uv,
                   "textures_same": C.texture_inventory(src) == src_tex},
        "apose": {"head_z": round(P["head"][1], 5),
                  "hip_z": round(P["hip"][1], 5),
                  "shoulder_z": round(P["shoulder"][1], 5)},
    }
    log("CHAIN " + json.dumps(info, ensure_ascii=False)[:900])
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:]
                         if "--" in sys.argv else [])

    t0 = time.time()
    base_mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    gain_mapping = copy.deepcopy(base_mapping)
    gain_mapping["arm_gain_deg"] = {
        k: v * ARM_GAIN for k, v in base_mapping["arm_gain_deg"].items()}
    ch = build_chain()

    # 站架恒等：换用 player A-pose 后仍不许把模型扭成格斗站架。
    C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                 None, 0, gain_mapping)
    stance_pos, _ = C.evaluated(ch["src"])
    max_stance = max((a - b).length
                     for a, b in zip(ch["rest_pos"], stance_pos))
    identical = max_stance < 1e-5
    log(f"STANCE_IDENTITY max={max_stance:.9f} identical={identical}")
    assert identical, "player A-pose rig must not deform at stance"

    def metrics(card, frame, mapping):
        C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                     card, frame, mapping)
        pos, _ = C.evaluated(ch["src"])
        return C2.frame_metrics(ch["rest_pos"], ch["rest_edges"], pos,
                                ch["hf"], ch["hb"], ch["foot"],
                                ch["hip_z"], ch["sh_z"])

    shots = []
    shots_spec = PROBE_SHOTS if args.probe else KEY_SHOTS
    for name, card, frame, _deg in shots_spec:
        C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                     card, frame, gain_mapping)
        png = render(ch, f"e-{name}-x15")
        png.update({"shot": name, "card": card, "frame": frame,
                    "tag": "E_x15"})
        shots.append(png)
        log(f"SHOT {png['file']} bytes={png['bytes']}")
    C.pose_frame(ch["rig"], ch["P"], ch["table"], ch["stance"],
                 None, 0, gain_mapping)
    side = render(ch, "e-stance-angle55", 55.0)
    side.update({"shot": "stance-angle55", "card": None, "frame": 0,
                 "tag": "E_x15", "angle_deg": 55.0})
    shots.append(side)

    if args.probe:
        one = metrics("cross", 10, gain_mapping)
        report = {
            "blender": bpy.app.version_string,
            "method": "player V4b A-pose rig + Voxel shell + SURFACE_DEFORM",
            "params": {"voxel_size": VOXEL, "arm_only_gain": ARM_GAIN,
                       "apose_table": "player"},
            "chain": ch["info"],
            "stance_identity": {"identical": identical,
                                "max_vertex_delta_m": round(max_stance, 9)},
            "one_frame_cross10": one,
            "shots": shots,
            "elapsed_seconds": round(time.time() - t0, 2),
        }
        PROBE_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        log(f"E_PROBE_OK shots={len(shots)} cross10={one} "
            f"elapsed={report['elapsed_seconds']}s")
        return 0

    # --- 全 72 帧 × 两组增益，与 A 路线 A2_x15 同帧对照 ---------------------
    a_report = json.loads(A_REPORT.read_text(encoding="utf-8"))
    a_by_key = {(r["card"], r["frame"]): r
                for r in a_report["all_frames"]["rows"]}
    rows = []
    for cid, n in CARDS:
        for f in range(n):
            m_x1 = metrics(cid, f, base_mapping)
            m_x15 = metrics(cid, f, gain_mapping)
            ref = a_by_key[(cid, f)]["A2_x15"]
            rows.append({
                "card": cid, "frame": f,
                "E_x1": m_x1, "E_x15": m_x15,
                "A2_x15_foe": {k: ref[k] for k in m_x1},
            })
        log(f"METRICS {cid} {n} frames elapsed={time.time() - t0:.1f}s")

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND), compress=True)
    blend_bytes = OUT_BLEND.read_bytes()
    export = {"file": OUT_BLEND.name, "bytes": len(blend_bytes),
              "sha256": hashlib.sha256(blend_bytes).hexdigest()}

    # 重开验证：bind / 骨架 / packed 贴图随文件走，且真的能驱动。
    bpy.ops.wm.open_mainfile(filepath=str(OUT_BLEND))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    hi = next(o for o in meshes if any(m.type == "SURFACE_DEFORM"
                                       for m in o.modifiers))
    sd = next(m for m in hi.modifiers if m.type == "SURFACE_DEFORM")
    rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    imgs = [im for im in bpy.data.images
            if im.source == "FILE" and tuple(im.size) == (4096, 4096)]
    rest2, _ = C.evaluated(hi)
    C.pose_frame(rigs[0], ch["P"], ch["table"], ch["stance"],
                 "cross", 10, gain_mapping)
    posed2, _ = C.evaluated(hi)
    reopen = {
        "surface_deform_is_bound": bool(getattr(sd, "is_bound", False)),
        "surface_deform_target": sd.target.name if sd.target else None,
        "rig_count": len(rigs),
        "rig_bones": len(rigs[0].pose.bones) if rigs else 0,
        "high_poly_verts": len(hi.data.vertices),
        "high_poly_uv_layers": len(hi.data.uv_layers),
        "packed_4096_textures": sum(1 for im in imgs if im.packed_file),
        "textures_4096": len(imgs),
        "reopen_drive_max_displacement_m": round(
            max((a - b).length for a, b in zip(rest2, posed2)), 5),
    }
    log("REOPEN " + json.dumps(reopen, ensure_ascii=False))

    report = {
        "blender": bpy.app.version_string,
        "fingerprints": {k: hashlib.sha256(p.read_bytes()).hexdigest()
                         for k, p in (("source_blend", BLEND),
                                      ("table", TABLE), ("spec", SPEC),
                                      ("mapping", MAPPING),
                                      ("a_report", A_REPORT),
                                      ("c_build_py", BAKE / "C路线-真3D修复" / "c_build.py"))},
        "method": "player V4b A-pose rest 13 bones (apose_joints.player) "
                  "+ Voxel continuous shell (triangulated) + ARMATURE_AUTO "
                  "+ SURFACE_DEFORM bind; original 2,035-shell high-poly "
                  "keeps UV / 3 packed 4096 PBR textures",
        "params": {"voxel_size": VOXEL, "arm_only_gain": ARM_GAIN,
                   "apose_table": "player"},
        "chain": ch["info"],
        "stance_identity": {"identical": identical,
                            "max_vertex_delta_m": round(max_stance, 9)},
        "export": export,
        "reopen": reopen,
        "all_frames": {"count": len(rows),
                       "cards": {k: n for k, n in CARDS}, "rows": rows},
        "shots": shots,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    log(f"E_BUILD_OK frames={len(rows)} shots={len(shots)} "
        f"blend_bytes={export['bytes']} elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
