"""C 路线 V2：A-pose 权重领地修正 + 全 72 帧变形质量门禁。

显式 import route-c-real-3d-fix/c_build.py 复用整条链路（A-pose rest 13 骨、
Voxel 连续壳、ARMATURE_AUTO、Data Transfer、相对 rest 增量驱动、retarget），
保证「同一公式只有一个真相来源」。本脚本只加两层：

  1. territory refinement（本轮真正修的东西）
     Data Transfer 用 POLYINTERP_NEAREST 把代理壳**表面**权重贴回高模。
     高模有 2,809 个开放薄壳，很多顶点落到错误肢体附近，于是手臂顶点掺进
     chest/hips 的权重 —— 一动手臂就被整片摊薄，看图三档几乎一样。
     按 A-pose rest 骨段给每个顶点定 owner 族（arm_f/arm_b/torso/leg_*），
     跨族权重乘 ALPHA，肩髋桥接骨乘 BETA，再归一化。

  2. 全帧质量度量（不只是 jab#8 一帧）
     jab/cross/wave 共 72 帧，四组单变量对照：
       V1_base  原权重 + x1.0        （C 路线现状）
       V1_gain  原权重 + x1.5 arm-only（只看增益）
       V2_base  领地修正 + x1.0      （只看权重）
       V2_final 领地修正 + x1.5      （定稿）
     逐帧量：边撕裂 p999 / >5cm 边数、手腕簇位移、脚底贴地偏差、
     手-躯干穿透比例、最大骨角。把「变形质量」从一句话变成可复算数字。

不回写任何既有归档，不进 Godot，不改游戏源码。
用法（Blender 5.2.3）：
  blender.exe -b --python c2_build.py -- --probe
  blender.exe -b --python c2_build.py -- --shots
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "route-c-real-3d-fix"))
import c_build as C  # noqa: E402  - 复用同一条链路，不复制公式

TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3d-attack-gifs" / "apose_joints.json"
MAPPING = BAKE / "3d-attack-gifs" / "puppet_mapping.json"
BLEND = BAKE / "foe-blender-modeling-v1" / "foe-V1.blend"

# 权重领地修正参数：跨族压到 10%，肩/髋桥接骨保留 45%
ALPHA = 0.10
BETA = 0.45
# C 路线增益 sweep 看图给出的可用区间上沿，且只放大 arm_gain_deg
ARM_GAIN = 1.5

HAND_CLUSTER_N = 160
FOOT_PCT = 0.01
TORSO_HALF_X = 0.22
TORSO_HALF_Y = 0.25

FAMILY = {
    "hips": "torso", "spine": "torso", "chest": "torso",
    "neck": "torso", "head": "torso",
    "upperarm_f": "arm_f", "forearm_f": "arm_f",
    "upperarm_b": "arm_b", "forearm_b": "arm_b",
    "thigh_f": "leg_f", "shin_f": "leg_f",
    "thigh_b": "leg_b", "shin_b": "leg_b",
}
BRIDGE = {"chest", "hips", "upperarm_f", "upperarm_b",
          "thigh_f", "thigh_b"}
CARDS = (("jab", 14), ("cross", 22), ("wave", 36))

PROBE_SHOTS = [
    ("jab07", "jab", 6, 0.0),
    ("cross11", "cross", 10, 0.0),
    ("wave18", "wave", 17, 0.0),
]
FULL_SHOTS = [
    ("stance", None, 0, 0.0),
    ("jab01", "jab", 0, 0.0), ("jab07", "jab", 6, 0.0),
    ("jab13", "jab", 12, 0.0),
    ("cross01", "cross", 0, 0.0), ("cross11", "cross", 10, 0.0),
    ("cross21", "cross", 20, 0.0),
    ("wave01", "wave", 0, 0.0), ("wave18", "wave", 17, 0.0),
    ("wave35", "wave", 34, 0.0),
]


def log(*a):
    print(*a, flush=True)


def seg_dist(p, a, b):
    ab = b - a
    den = ab.length_squared
    t = max(0.0, min(1.0, (p - a).dot(ab) / den)) if den > 1e-12 else 0.0
    return (p - (a + t * ab)).length


def segments(P):
    return [(n, Vector((P[u][0], 0.0, P[u][1])),
             Vector((P[v][0], 0.0, P[v][1])))
            for n, _p, u, v in C.CHAIN]


def owner_families(obj, segs):
    """每个顶点最近的 A-pose rest 骨段决定它属于哪条肢体。"""
    out = []
    for v in obj.data.vertices:
        p = obj.matrix_world @ v.co
        out.append(FAMILY[min(segs, key=lambda s: seg_dist(p, s[1], s[2]))[0]])
    return out


def purity(obj, owners):
    """owner 族内的权重占比。1.0 = 该顶点完全由自己那条肢体驱动。"""
    g2n = {g.index: g.name for g in obj.vertex_groups}
    acc = {}
    for i, v in enumerate(obj.data.vertices):
        tot = sum(g.weight for g in v.groups)
        if tot <= 1e-9:
            continue
        fam = owners[i]
        own = sum(g.weight for g in v.groups
                  if FAMILY.get(g2n.get(g.group, "")) == fam)
        n, s = acc.get(fam, (0, 0.0))
        acc[fam] = (n + 1, s + own / tot)
    return {k: {"verts": n, "mean_own_weight": round(s / n, 5)}
            for k, (n, s) in sorted(acc.items())}


def refine(obj, owners):
    """按 owner 族压掉跨肢体权重并归一化。用 bmesh deform layer 批量写。"""
    g2n = {g.index: g.name for g in obj.vertex_groups}
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    dl = bm.verts.layers.deform.verify()
    changed = 0
    dropped = 0
    for v in bm.verts:
        dv = v[dl]
        old = {gi: float(dv[gi]) for gi in dv.keys()}
        if not old:
            continue
        fam = owners[v.index]
        new = {}
        for gi, w in old.items():
            bone = g2n.get(gi, "")
            if FAMILY.get(bone) == fam:
                f = 1.0
            elif bone in BRIDGE:
                f = BETA
            else:
                f = ALPHA
            nw = w * f
            if nw > 1e-6:
                new[gi] = nw
        if not new:
            continue
        s = sum(new.values())
        for gi in list(dv.keys()):
            del dv[gi]
        for gi, w in new.items():
            dv[gi] = w / s
        changed += 1
        dropped += len(old) - len(new)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return {"changed_vertices": changed, "dropped_assignments": dropped}


def clone(src, name):
    obj = src.copy()
    obj.data = src.data.copy()
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    obj.hide_render = True
    return obj


def clusters(coords, P):
    def nearest(pt, n):
        t = Vector((pt[0], 0.0, pt[1]))
        return sorted(range(len(coords)),
                      key=lambda i: (coords[i] - t).length_squared)[:n]
    hf = nearest(P["f_hand"], HAND_CLUSTER_N)
    hb = nearest(P["b_hand"], HAND_CLUSTER_N)
    nf = max(1, int(len(coords) * FOOT_PCT))
    foot = sorted(range(len(coords)), key=lambda i: coords[i].z)[:nf]
    return hf, hb, foot


def frame_metrics(rest, edges, posed, hf, hb, foot, hip_z, sh_z):
    tear = C.tear_stats(rest, posed, edges)
    disp = C.displacement_stats(rest, posed)
    reach_f = sum((posed[i] - rest[i]).length for i in hf) / len(hf)
    reach_b = sum((posed[i] - rest[i]).length for i in hb) / len(hb)
    zr = sum(rest[i].z for i in foot) / len(foot)
    zp = sum(posed[i].z for i in foot) / len(foot)
    pen = 0
    for i in hf + hb:
        p = posed[i]
        if (abs(p.x) < TORSO_HALF_X and hip_z - 0.05 < p.z < sh_z + 0.05
                and abs(p.y) < TORSO_HALF_Y):
            pen += 1
    return {
        "tear_p999_m": tear["p999_edge_tear_m"],
        "tear_gt5cm": tear["edges_gt_5cm"],
        "max_displacement_m": disp["max_displacement_m"],
        "moved_gt_1mm": disp["moved_gt_1mm"],
        "reach_f_m": round(reach_f, 5),
        "reach_b_m": round(reach_b, 5),
        "reach_max_m": round(max(reach_f, reach_b), 5),
        "foot_gap_m": round(abs(zp - zr), 5),
        "penetration_pct": round(pen / (len(hf) + len(hb)), 5),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:]
                         if "--" in sys.argv else [])

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    base_mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    mapping_gain = copy.deepcopy(base_mapping)
    mapping_gain["arm_gain_deg"] = {
        k: v * ARM_GAIN for k, v in base_mapping["arm_gain_deg"].items()}
    stance = C.joints_of(table, None, 0)
    P = C.apose_points(spec)
    assert BLEND.is_file(), f"missing {BLEND}"

    t0 = time.time()
    fingerprints = {k: hashlib.sha256(p.read_bytes()).hexdigest()
                    for k, p in (("blend", BLEND), ("table", TABLE),
                                 ("spec", SPEC), ("mapping", MAPPING),
                                 ("c_build_py", BAKE / "route-c-real-3d-fix" / "c_build.py"))}
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    for o in list(scene.objects):
        if o.type == "ARMATURE":
            bpy.data.objects.remove(o, do_unlink=True)
    src.hide_render = True
    src_tex, src_uv = C.texture_inventory(src), len(src.data.uv_layers)
    log(f"OPEN src={src.name} verts={len(src.data.vertices)} uv={src_uv}")

    # --- 1. 与 C 路线完全相同的 A-pose rest 13 骨 ----------------------------
    arm_data = bpy.data.armatures.new("c2_apose_rig")
    rig = bpy.data.objects.new("c2_apose_rig", arm_data)
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
    log(f"APOSE_RIG bones={len(rig.pose.bones)}")

    # --- 2. Voxel 连续壳 + 自动权重 + Data Transfer --------------------------
    proxy = C.fresh_copy(src, "c2_voxel_proxy")
    proxy.data.remesh_voxel_size = C.VOXEL
    proxy.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy
    assert bpy.ops.object.voxel_remesh.poll()
    bpy.ops.object.voxel_remesh()
    proxy_v = len(proxy.data.vertices)
    C.auto_weight(proxy, rig)
    proxy_covered = sum(1 for v in proxy.data.vertices
                        if any(g.weight > 1e-6 for g in v.groups))
    log(f"PROXY verts={proxy_v} covered={proxy_covered}")

    base = C.fresh_copy(src, "c2_base")
    for b in rig.data.bones:
        base.vertex_groups.new(name=b.name)
    mod = base.modifiers.new("weights_from_voxel_proxy", "DATA_TRANSFER")
    mod.object = proxy
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    mod.layers_vgroup_select_src = "ALL"
    mod.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.select_all(action="DESELECT")
    base.select_set(True)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=mod.name)
    base.modifiers.new("c2_armature", "ARMATURE").object = rig
    covered = sum(1 for v in base.data.vertices
                  if any(g.weight > 1e-6 for g in v.groups))
    log(f"BASE covered={covered}/{len(base.data.vertices)}")

    # --- 3. V1 / V2 双副本 + 领地修正 ----------------------------------------
    v1 = clone(base, "c2_v1_original")
    v2 = clone(base, "c2_v2_refined")
    segs = segments(P)
    coords = [v2.matrix_world @ v.co for v in v2.data.vertices]
    owners = owner_families(v2, segs)
    purity_v1 = purity(v1, owners)
    refine_info = refine(v2, owners)
    purity_v2 = purity(v2, owners)
    assets = {"uv_layers": len(v2.data.uv_layers),
              "materials": len(v2.data.materials),
              "textures": C.texture_inventory(v2),
              "uv_same": len(v2.data.uv_layers) == src_uv,
              "textures_same": C.texture_inventory(v2) == src_tex}
    log(f"PURITY_V1 {json.dumps(purity_v1)}")
    log(f"PURITY_V2 {json.dumps(purity_v2)}")
    log(f"REFINE {json.dumps(refine_info)} ASSETS {assets['uv_same']}/{assets['textures_same']}")

    meshes = (src, proxy, base, v1, v2)

    def show_only(obj):
        for o in meshes:
            o.hide_render = o is not obj

    C.setup_camera(scene, 0.0)
    rest_pos, rest_edges = C.evaluated(v2)
    hf, hb, foot = clusters(rest_pos, P)
    hip_z, sh_z = P["hip"][1], P["shoulder"][1]
    log(f"CLUSTERS hand_f={len(hf)} hand_b={len(hb)} foot={len(foot)} "
        f"edges={len(rest_edges)}")

    # --- 4. 站架恒等（V2 修正后仍不许把 A-pose 扭成站架）--------------------
    C.pose_frame(rig, P, table, stance, None, 0, mapping_gain)
    stance_pos, _ = C.evaluated(v2)
    sd = [(a - b).length for a, b in zip(rest_pos, stance_pos)]
    max_stance = max(sd)
    identical = max_stance < 1e-5
    log(f"STANCE_IDENTITY max={max_stance:.9f} identical={identical}")
    assert identical, "refined weights must not deform the A-pose at stance"

    # --- 5. 全 72 帧 × 四组单变量对照 ---------------------------------------
    rows = []
    for cid, n in CARDS:
        for f in range(n):
            row = {"card": cid, "frame": f}
            for mtag, mapping in (("base", base_mapping), ("gain", mapping_gain)):
                _d, _r, sig = C.pose_frame(rig, P, table, stance, cid, f, mapping)
                for otag, obj in (("V1", v1), ("V2", v2)):
                    pos, _ = C.evaluated(obj)
                    m = frame_metrics(rest_pos, rest_edges, pos,
                                      hf, hb, foot, hip_z, sh_z)
                    m["max_delta_deg"] = sig["mapped_max_abs_deg"]
                    row[f"{otag}_{mtag}"] = m
            # V2 + x1.5 是本轮定稿配置，给它一个稳定名字，别让下游猜。
            row["V2_final"] = row.pop("V2_gain")
            rows.append(row)
        log(f"METRICS {cid} {n} frames done elapsed={time.time()-t0:.1f}s")
    log(f"ALL_FRAMES rows={len(rows)}")

    # --- 6. 代表帧渲染（同帧同相机，V1/V2 并排）-----------------------------
    def render(name, obj, deg=0.0):
        C.setup_camera(scene, deg)
        show_only(obj)
        path = HERE / "frames" / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        b = path.read_bytes()
        assert b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 10000
        return {"file": path.name, "bytes": len(b),
                "sha256": hashlib.sha256(b).hexdigest()}

    if args.shots:
        # 定稿对照：同一份 C 路线原始平滑权重，只改 arm-only 增益。
        # V2（领地修正）被全帧数据证伪（幅度零贡献、撕裂 1.89x），不进定稿图。
        pairs = (("A_x1", v1, base_mapping), ("B_x15", v1, mapping_gain))
        shots = FULL_SHOTS
    else:
        # 探针图保留 V2 作为「试过并否掉」的视觉证据。
        pairs = (("V1", v1, base_mapping), ("V2", v2, mapping_gain))
        shots = PROBE_SHOTS
    outputs = []
    for name, card, frame, _deg in shots:
        for tag, obj, mapping in pairs:
            d, r, sig = C.pose_frame(rig, P, table, stance, card, frame, mapping)
            png = render(f"{name}-{tag}", obj, 0.0)
            png.update({"tag": tag, "shot": name, "card": card, "frame": frame,
                        "max_delta_deg": sig["mapped_max_abs_deg"]})
            outputs.append(png)
            log(f"SHOT {name}-{tag} bytes={png['bytes']}")
    if args.probe or args.shots:
        # 侧视必须显式回到站架，否则沿用上面循环最后一帧的 pose，
        # 名字写着 stance 实际渲的是 wave#35 —— 这条坑在 probe 版踩过。
        C.pose_frame(rig, P, table, stance, None, 0, mapping_gain)
        side_obj = v1 if args.shots else v2
        side_tag = "B_x15" if args.shots else "V2"
        png = render(f"stance-{side_tag}-angle55", side_obj, 55.0)
        png.update({"tag": side_tag, "shot": "stance-angle55", "card": None,
                    "frame": 0, "angle_deg": 55.0})
        outputs.append(png)
        log(f"SHOT stance-{side_tag}-angle55 bytes={png['bytes']}")

    report = {
        "blender": bpy.app.version_string,
        "fingerprints": fingerprints,
        "method": "explicit import of route-c-real-3d-fix/c_build.py (same retarget "
                  "formula) + A-pose territory weight refinement "
                  "+ 72-frame four-variant quality metrics",
        "params": {"alpha_cross_family": ALPHA, "beta_bridge": BETA,
                   "arm_only_gain": ARM_GAIN, "hand_cluster_n": HAND_CLUSTER_N,
                   "foot_pct": FOOT_PCT, "torso_half_x": TORSO_HALF_X,
                   "torso_half_y": TORSO_HALF_Y, "bridge_bones": sorted(BRIDGE)},
        "rig": {"bones": len(rig.pose.bones),
                "names": sorted(rig.pose.bones.keys())},
        "proxy": {"voxel_size": C.VOXEL, "verts": proxy_v,
                  "auto_weight_covered": proxy_covered},
        "weights": {"covered": covered,
                    "verts": len(v2.data.vertices),
                    "owner_families": {f: owners.count(f) for f in sorted(set(owners))},
                    "v1_purity": purity_v1, "v2_purity": purity_v2,
                    "refine": refine_info},
        "assets": assets,
        "stance_identity": {"vertices_identical": identical,
                            "tolerance_m": 1e-5,
                            "max_vertex_delta_m": round(max_stance, 9)},
        "clusters": {"hand_f": len(hf), "hand_b": len(hb), "foot": len(foot),
                     "hip_z": round(hip_z, 5), "shoulder_z": round(sh_z, 5)},
        "all_frames": {"count": len(rows), "cards": {k: n for k, n in CARDS},
                       "rows": rows},
        "shots": outputs,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    (HERE / "c2_build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"C2_BUILD_OK frames={len(rows)} shots={len(outputs)} "
        f"elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
