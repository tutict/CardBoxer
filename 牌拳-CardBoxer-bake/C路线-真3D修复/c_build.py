"""C 路线 P0：修连续壳拓扑 + 平滑权重 + A-pose rest 对齐 + 增量驱动。

上一轮（3D攻击GIF/）真 3D 网格一动就撕，三个原因叠在一起：
  1. 模型是 A-pose，骨架 rest 却是格斗站架（boxer_rig.BONES）；
  2. 权重按「最近骨段刚性 1.0」分配，2,809 个开放薄壳被整片带走；
  3. 驱动方式是**绝对骨位** `pb.matrix = 摆到 baked2.json 的坐标`，
     等于把 A-pose 模型硬扭成站架 —— 连站架帧都已经折叠。

本脚本逐个拆掉：
  1. 用 3D攻击GIF/apose_joints.json 的正面标定换算成 Blender 3D，
     重建与模型形状对齐的 13 骨 A-pose rest 骨架；
  2. Voxel 0.020 -> 连续壳（2,809 壳 -> 3 壳）-> ARMATURE_AUTO 平滑权重
     -> Data Transfer 传回 64,024 顶点高模，UV / 3 张 4096² PBR 全保留；
  3. 改成**相对 rest 的增量驱动**：每帧只算 baked2.json 相对站架的
     骨角度差（wrap 到 ±pi），绕各自 rest head 做层级 RotY，绝不绝对摆位。
     站架帧 delta=0，复合变换恒等 —— 这是最硬的承重证据。
  4. 光有 1-3 还不够：实测逐骨原始角度差会让 hips/spine/chest 各拿同一个
     19.96°/27.18° 并累积三次，整个人斜转甚至横躺；cross 后手 -147.62°、
     wave 后臂 +162.08° 是侧视动作表语义。必须复用 3D攻击GIF 已看图验证的
     retarget 层（puppet_mapping.json，同参数同公式），只去掉 2D 专用前臂放大。

新增撕裂的量化判据：相邻顶点位移差（edge tear）。
  刚性权重会把壳边界两侧顶点分给不同骨，位移差巨大；
  平滑权重应把这个数压下来。同一帧对 smooth / rigid 两个副本做 A/B。

只读既有 .blend，不回写任何归档，不进 Godot，不改游戏源码。
用法：
  blender -b --python c_build.py -- --probe
  blender -b --python c_build.py -- --full
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3D攻击GIF" / "apose_joints.json"
MAPPING = BAKE / "3D攻击GIF" / "puppet_mapping.json"
BLEND = BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"
VOXEL = 0.020
PX_PER_M = 768 / 2.30
TARGET_Z = 0.86
JOINTS = ("hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow",
          "b_hand", "f_knee", "f_foot", "b_knee", "b_foot")

# name, parent, head point, tail point
CHAIN = [
    ("hips", None, "A", "B"),
    ("spine", "hips", "B", "C"),
    ("chest", "spine", "C", "D"),
    ("neck", "chest", "D", "E"),
    ("head", "neck", "E", "F"),
    ("upperarm_f", "chest", "D", "f_elbow"),
    ("forearm_f", "upperarm_f", "f_elbow", "f_hand"),
    ("upperarm_b", "chest", "D", "b_elbow"),
    ("forearm_b", "upperarm_b", "b_elbow", "b_hand"),
    ("thigh_f", "hips", "tf_head", "f_knee"),
    ("shin_f", "thigh_f", "f_knee", "f_foot"),
    ("thigh_b", "hips", "tb_head", "b_knee"),
    ("shin_b", "thigh_b", "b_knee", "b_foot"),
]


def log(*a):
    print(*a, flush=True)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def angle(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])


def wrap_pi(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def joints_of(table, card, frame):
    if card is None:
        return {k: tuple(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: tuple(tracks[card]["track"][frame][k]) for k in JOINTS}


def make_points(j):
    hip, sh, hd = j["hip"], j["shoulder"], j["head"]
    return {
        "A": hip, "B": lerp(hip, sh, 0.26), "C": lerp(hip, sh, 0.60),
        "D": sh, "E": lerp(sh, hd, 0.58), "F": hd,
        "f_elbow": j["f_elbow"], "f_hand": j["f_hand"],
        "b_elbow": j["b_elbow"], "b_hand": j["b_hand"],
        "f_knee": j["f_knee"], "f_foot": j["f_foot"],
        "b_knee": j["b_knee"], "b_foot": j["b_foot"],
        "tf_head": (hip[0] + 4.0, hip[1]),
        "tb_head": (hip[0] - 4.0, hip[1]),
    }


def to_xz(p):
    """768² 正面立绘坐标 -> Blender 世界 (x, z)，相机 ortho 2.30m / z=0.86m。"""
    return ((p[0] - 384) / PX_PER_M, TARGET_Z - (p[1] - 384) / PX_PER_M)


def apose_points(spec):
    J = {k: to_xz(v) for k, v in spec["foe"].items()}
    hip, sh, hd = J["hip"], J["shoulder"], J["head"]
    P = dict(J)
    P.update({
        "A": hip, "B": lerp(hip, sh, 0.26), "C": lerp(hip, sh, 0.60),
        "D": sh, "E": lerp(sh, hd, 0.58), "F": hd,
        # 4 game px = 0.04 m；与 make_puppet.py 的 tf_head/tb_head 同口径
        "tf_head": (hip[0] + 0.04, hip[1]),
        "tb_head": (hip[0] - 0.04, hip[1]),
    })
    return P


def clamp(v, cap):
    return max(-cap, min(cap, v))


def retarget_delta(frame_j, stance_j, mapping):
    """与 3D攻击GIF/make_puppet.py:retarget 完全同公式的侧视->正视重定向。

    C 路线第一版直接用逐骨原始角度差，结果 hips/spine/chest 各拿到同一个
    19.96°/27.18° 并在层级里累积三次，整个人斜转 60°/81°、cross 横躺；
    cross 后手 -147.62°、wave 后臂 +162.08° 更是侧视语义（f/b 是前后手）
    与正视 A-pose 模型不对齐。这里原样复用已看图验证过的 retarget 参数，
    只去掉 2D 图像专用的「前臂放大」透视（3D 网格不需要）。

    角度符号：game px 与 768² 画布都是 y 向下为正，mRotY(delta) 的正方向
    同样把 +x 转向下方，故 puppet 的弧度值可直接喂给 mRotY。
    """
    fp, sp = make_points(frame_j), make_points(stance_j)
    raw = {n: math.degrees(wrap_pi(angle(fp[u], fp[v]) - angle(sp[u], sp[v])))
           for n, _p, u, v in CHAIN}
    torso = math.degrees(wrap_pi(angle(fp["A"], fp["D"]) - angle(sp["A"], sp["D"])))
    torso_used = clamp(torso * mapping["torso_gain"], mapping["torso_cap_deg"])
    mf = math.dist(frame_j["f_hand"], stance_j["f_hand"])
    mb = math.dist(frame_j["b_hand"], stance_j["b_hand"])
    tf = min(1.0, mf / mapping["reach_norm_px"])
    tb = min(1.0, mb / mapping["reach_norm_px"])
    tw = min(1.0, min(mf, mb) / mapping["wave_min_norm_px"]) * mapping["wave_arm_weight"]
    af, ab = max(tf, tw), max(tb, tw)
    g, leg_cap = mapping["arm_gain_deg"], mapping["leg_cap_deg"]
    delta = {
        "hips": 0.0,
        "spine": math.radians(torso_used),
        "chest": 0.0,
        "neck": 0.0,
        "head": math.radians(-torso_used * mapping["head_compensation"]),
        "upperarm_f": math.radians(-g["f_upper"] * af),
        "forearm_f": math.radians(-g["f_fore"] * af),
        "upperarm_b": math.radians(g["b_upper"] * ab),
        "forearm_b": math.radians(g["b_fore"] * ab),
        "thigh_f": math.radians(clamp(raw["thigh_f"], leg_cap)),
        "shin_f": math.radians(clamp(raw["shin_f"], leg_cap)),
        "thigh_b": math.radians(clamp(raw["thigh_b"], leg_cap)),
        "shin_b": math.radians(clamp(raw["shin_b"], leg_cap)),
    }
    signals = {"torso_raw_deg": round(torso, 3),
               "torso_used_deg": round(torso_used, 3),
               "arm_f": round(af, 4), "arm_b": round(ab, 4),
               "raw_max_abs_deg": round(max(abs(v) for v in raw.values()), 3),
               "mapped_max_abs_deg": round(max(abs(math.degrees(v))
                                               for v in delta.values()), 3)}
    return delta, signals


def mRotY(theta):
    c, s = math.cos(theta), math.sin(theta)
    return Matrix(((c, 0.0, s, 0.0), (0.0, 1.0, 0.0, 0.0),
                   (-s, 0.0, c, 0.0), (0.0, 0.0, 0.0, 1.0)))


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


def texture_inventory(obj):
    out = []
    for slot in obj.material_slots:
        mat = slot.material
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    out.append({"image": n.image.name, "size": list(n.image.size)})
    return out


def evaluated(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = ev.to_mesh()
    pos = [(ev.matrix_world @ v.co).copy() for v in m.vertices]
    edges = [(e.vertices[0], e.vertices[1]) for e in m.edges]
    ev.to_mesh_clear()
    return pos, edges


def tear_stats(rest, posed, edges):
    """相邻顶点位移差：刚性分块会在壳边界撕出巨大跳变，平滑权重应压住它。"""
    disp = [posed[i] - rest[i] for i in range(len(rest))]
    ds = [(disp[a] - disp[b]).length for a, b in edges]
    ds.sort()
    n = len(ds)
    return {
        "edges": n,
        "max_edge_tear_m": round(ds[-1], 5),
        "p999_edge_tear_m": round(ds[int(n * 0.999)], 5),
        "p99_edge_tear_m": round(ds[int(n * 0.99)], 5),
        "mean_edge_tear_m": round(sum(ds) / n, 5),
        "edges_gt_2cm": sum(1 for d in ds if d > 0.02),
        "edges_gt_5cm": sum(1 for d in ds if d > 0.05),
    }


def displacement_stats(rest, posed):
    d = [(a - b).length for a, b in zip(rest, posed)]
    return {"vertices": len(d),
            "moved_gt_1mm": sum(1 for x in d if x > 1e-3),
            "max_displacement_m": round(max(d), 5),
            "mean_displacement_m": round(sum(d) / len(d), 5)}


def pose_frame(arm, P, table, stance, card, frame, mapping):
    """相对 rest 的层级增量旋转；绝不把骨绝对摆到站架坐标。"""
    j = joints_of(table, card, frame)
    delta, signals = retarget_delta(j, stance, mapping)
    dx = (j["hip"][0] - stance["hip"][0]) / 100.0
    dz = -(j["hip"][1] - stance["hip"][1]) / 100.0
    base = Matrix.Translation(Vector((dx, 0.0, dz)))
    D = {}
    for name, parent, u, _v in CHAIN:
        hx, hz = P[u]
        hv = Vector((hx, 0.0, hz))
        local = (Matrix.Translation(hv) @ mRotY(delta[name])
                 @ Matrix.Translation(-hv))
        D[name] = (base if parent is None else D[parent]) @ local
        pb = arm.pose.bones[name]
        pb.matrix = D[name] @ pb.bone.matrix_local
        bpy.context.view_layer.update()
    return delta, (dx, dz), signals


def setup_camera(scene, deg, res=768):
    cam = next(o for o in scene.objects if o.type == "CAMERA")
    a, R, tz = math.radians(deg), 4.0, TARGET_Z
    cam.location = (R * math.sin(a), -R * math.cos(a), tz)
    cam.rotation_euler = (Vector((0.0, 0.0, tz)) - cam.location).to_track_quat(
        "-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.30
    scene.camera = cam
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    return cam


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--gif", action="store_true",
                    help="渲 jab/cross/wave 全 72 帧，供拼真 3D 攻击 GIF")
    ap.add_argument("--sweep", action="store_true",
                    help="多档 retarget 增益的幅度/撕裂权衡探针，只写 gain_sweep_blender.json")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:]
                         if "--" in sys.argv else [])

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    stance = joints_of(table, None, 0)
    P = apose_points(spec)
    assert BLEND.is_file(), f"missing {BLEND}"

    t0 = time.time()
    blend_sha = hashlib.sha256(BLEND.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    old_rig_name = next(o for o in scene.objects if o.type == "ARMATURE").name
    for o in list(scene.objects):
        if o.type == "ARMATURE":
            bpy.data.objects.remove(o, do_unlink=True)
    log(f"OPEN src={src.name} verts={len(src.data.vertices)} "
        f"old_rig={old_rig_name} removed")
    src_tex, src_uv = texture_inventory(src), len(src.data.uv_layers)

    # --- 1. A-pose rest 13 骨 ------------------------------------------------
    arm_data = bpy.data.armatures.new("c_apose_rig")
    rig = bpy.data.objects.new("c_apose_rig", arm_data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for name, parent, u, v in CHAIN:
        eb = arm_data.edit_bones.new(name)
        hx, hz = P[u]
        tx, tz = P[v]
        eb.head = (hx, 0.0, hz)
        eb.tail = (tx, 0.0, tz)
        assert (eb.tail - eb.head).length > 1e-4, f"zero-length bone {name}"
        if parent:
            eb.parent = made[parent]
        made[name] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.bone.inherit_scale = "NONE"
    bpy.context.view_layer.update()
    log(f"APOSE_RIG bones={len(rig.pose.bones)} "
        f"head_top_z={P['head'][1]:.4f} hip_z={P['hip'][1]:.4f}")

    # --- 2. Voxel 连续壳 + 平滑权重 -----------------------------------------
    proxy = fresh_copy(src, "c_voxel_proxy")
    proxy.data.remesh_voxel_size = VOXEL
    proxy.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy
    assert bpy.ops.object.voxel_remesh.poll()
    bpy.ops.object.voxel_remesh()
    proxy_v, proxy_f = len(proxy.data.vertices), len(proxy.data.polygons)
    log(f"PROXY verts={proxy_v} faces={proxy_f}")
    auto_weight(proxy, rig)
    proxy_covered = sum(1 for v in proxy.data.vertices
                        if any(g.weight > 1e-6 for g in v.groups))
    log(f"PROXY auto_weight {proxy_covered}/{proxy_v}")

    # --- 3. Data Transfer 回传高模 -------------------------------------------
    final = fresh_copy(src, "c_smooth_final")
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
    final.modifiers.new("c_armature", "ARMATURE").object = rig
    covered = sum(1 for v in final.data.vertices
                  if any(g.weight > 1e-6 for g in v.groups))
    multi = sum(1 for v in final.data.vertices
                if sum(1 for g in v.groups if g.weight > 1e-6) >= 2)
    assets = {"uv_layers": len(final.data.uv_layers),
              "materials": len(final.data.materials),
              "textures": texture_inventory(final),
              "uv_same": len(final.data.uv_layers) == src_uv,
              "textures_same": texture_inventory(final) == src_tex}
    log(f"FINAL covered={covered}/{len(final.data.vertices)} "
        f"multi_bone_verts={multi} assets={assets['uv_same']}/{assets['textures_same']}")

    # --- 4. 刚性权重 A/B 对照副本 -------------------------------------------
    rigid = fresh_copy(src, "c_rigid_baseline")
    segs = [(n, Vector((P[u][0], 0.0, P[u][1])),
             Vector((P[v][0], 0.0, P[v][1]))) for n, _p, u, v in CHAIN]
    groups = {n: rigid.vertex_groups.new(name=n) for n, _a, _b in segs}

    def seg_dist(p, a, b):
        ab = b - a
        den = ab.length_squared
        t = max(0.0, min(1.0, (p - a).dot(ab) / den)) if den > 1e-12 else 0.0
        return (p - (a + t * ab)).length

    buckets = {n: [] for n, _a, _b in segs}
    for v in rigid.data.vertices:
        p = rigid.matrix_world @ v.co
        buckets[min(segs, key=lambda s: seg_dist(p, s[1], s[2]))[0]].append(v.index)
    for n, idx in buckets.items():
        if idx:
            groups[n].add(idx, 1.0, "REPLACE")
    rigid.modifiers.new("c_armature_rigid", "ARMATURE").object = rig
    bucket_counts = {k: len(v) for k, v in buckets.items()}
    log(f"RIGID buckets={bucket_counts}")

    setup_camera(scene, 0.0)
    meshes = (src, proxy, final, rigid)

    def show_only(obj):
        for o in meshes:
            o.hide_render = o is not obj

    def render(name, obj, deg=0.0):
        setup_camera(scene, deg)
        show_only(obj)
        path = HERE / "frames" / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        b = path.read_bytes()
        assert b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 10000
        return {"file": path.name, "bytes": len(b),
                "sha256": hashlib.sha256(b).hexdigest()}

    # --- 5. 站架恒等：未变形 vs 走完整驱动链 --------------------------------
    setup_camera(scene, 0.0)
    show_only(final)
    rest_pos, rest_edges = evaluated(final)
    rest_png = render("c-rest-unposed", final)
    delta0, root0, sig0 = pose_frame(rig, P, table, stance, None, 0, mapping)
    stance_pos, _ = evaluated(final)
    stance_png = render("c-stance-driven", final)
    stance_diffs = [(a - b).length for a, b in zip(rest_pos, stance_pos)]
    max_vertex_delta = max(stance_diffs)
    mean_vertex_delta = sum(stance_diffs) / len(stance_diffs)
    # 0.01 mm 工程容差：pb.matrix 往返有浮点漂移，但绝不允许出现可见变形
    TOLERANCE_M = 1e-5
    identical = max_vertex_delta < TOLERANCE_M
    log(f"STANCE_IDENTITY delta0={max(abs(v) for v in delta0.values()):.9f} "
        f"root0={root0} max_vertex_delta_m={max_vertex_delta:.9f} "
        f"mean={mean_vertex_delta:.9f} tol={TOLERANCE_M} identical={identical}")
    assert identical, "stance must not deform the A-pose mesh"

    # --- 6. A/B 撕裂度量（同一 jab#8 帧） -----------------------------------
    jab_delta, jab_root, jab_sig = pose_frame(
        rig, P, table, stance, "jab", 7, mapping)
    smooth_pos, _ = evaluated(final)
    rigid_pos, _ = evaluated(rigid)
    tear_smooth = tear_stats(rest_pos, smooth_pos, rest_edges)
    tear_rigid = tear_stats(rest_pos, rigid_pos, rest_edges)
    disp_smooth = displacement_stats(rest_pos, smooth_pos)
    disp_rigid = displacement_stats(rest_pos, rigid_pos)
    log(f"TEAR_SMOOTH {json.dumps(tear_smooth)}")
    log(f"TEAR_RIGID  {json.dumps(tear_rigid)}")
    ab_pngs = {
        "smooth": render("c-jab-smooth", final),
        "rigid": render("c-jab-rigid", rigid),
    }

    # --- 6b. 增益 sweep -----------------------------------------------------
    # 看图发现：平滑权重修好了撕裂，但动作幅度比 puppet 版明显小。原因是
    # mapping 里 arm_gain/torso_cap/leg_cap 是给 2D 纸片人调的，3D 网格
    # 的平滑权重会把同样的角度摊薄。这里对增益做倍率扫描，逐档量测
    # 「渲染像素变化幅度」与「边撕裂」，回答能不能放大而不撕。
    # 不覆盖 c_build.json / 既有 GIF，只新增 sweep 帧与独立报告。
    if args.sweep:
        import copy
        base = copy.deepcopy(mapping)
        # 全参数放大 x3.0 会把 torso_gain/cap 一起放大，看图整个人斜转 45°、
        # 手臂冲出画面。追加 arm_only 组：只放大 arm_gain_deg，torso/leg 不动，
        # 用来区分「动作幅度被手臂增益限制」与「躯干增益毁姿态」。
        configs = ([(g, "all") for g in (1.0, 1.5, 2.0, 3.0)]
                   + [(g, "arm_only") for g in (1.5, 2.0, 3.0)])
        sweep = []
        for gain, mode in configs:
            m = copy.deepcopy(base)
            m["arm_gain_deg"] = {k: v * gain
                                 for k, v in base["arm_gain_deg"].items()}
            if mode == "all":
                m["torso_gain"] = base["torso_gain"] * gain
                m["torso_cap_deg"] = base["torso_cap_deg"] * gain
                m["leg_cap_deg"] = base["leg_cap_deg"] * gain
            tag = f"g{gain:.1f}" if mode == "all" else f"arm-g{gain:.1f}"
            rows = []
            for cid, fr in (("jab", 7), ("cross", 11), ("wave", 18)):
                _d, _r, sig = pose_frame(rig, P, table, stance, cid, fr, m)
                pos, _ = evaluated(final)
                tear = tear_stats(rest_pos, pos, rest_edges)
                disp = displacement_stats(rest_pos, pos)
                png = render(f"sweep-{tag}-{cid}{fr:02d}", final)
                rows.append({"card": cid, "frame": fr,
                             "max_delta_deg": sig["mapped_max_abs_deg"],
                             "tear": tear, "displacement": disp, "png": png})
            sweep.append({"gain": gain, "mode": mode, "rows": rows})
            log(f"SWEEP {mode} gain={gain} " + " ".join(
                f"{r['card']}{r['frame']}:p999={r['tear']['p999_edge_tear_m']:.5f}"
                f" gt5cm={r['tear']['edges_gt_5cm']}" for r in rows))
        (HERE / "gain_sweep_blender.json").write_text(
            json.dumps({"sweep": sweep, "baseline_mapping_sha256":
                        hashlib.sha256(MAPPING.read_bytes()).hexdigest()},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        log("C_SWEEP_OK")
        return 0

    # --- 7. 代表帧 ----------------------------------------------------------
    if args.gif:
        shots = []
        for cid in ("jab", "cross", "wave"):
            for f in range(int(table["cards"][cid]["frames"])):
                shots.append((f"c-{cid}-f{f:03d}", cid, f, 0.0))
        shots.append(("c-stance-angle55", None, 0, 55.0))
    elif args.full:
        shots = [("c-jab-f04", "jab", 4, 0.0), ("c-jab-f07", "jab", 7, 0.0),
                 ("c-jab-f10", "jab", 10, 0.0), ("c-cross-f06", "cross", 6, 0.0),
                 ("c-cross-f11", "cross", 11, 0.0), ("c-cross-f16", "cross", 16, 0.0),
                 ("c-wave-f18", "wave", 18, 0.0), ("c-wave-f30", "wave", 30, 0.0),
                 ("c-stance-angle55", None, 0, 55.0)]
    else:
        shots = [("c-cross-f11", "cross", 11, 0.0),
                 ("c-wave-f18", "wave", 18, 0.0),
                 ("c-stance-angle55", None, 0, 55.0)]
    outputs = []
    for name, card, frame, deg in shots:
        d, r, sig = pose_frame(rig, P, table, stance, card, frame, mapping)
        png = render(name, final, deg)
        png.update({"card": card, "frame": frame, "angle_deg": deg,
                    "max_delta_deg": sig["mapped_max_abs_deg"],
                    "raw_max_delta_deg": sig["raw_max_abs_deg"],
                    "retarget_signals": sig,
                    "delta_deg": {k: round(math.degrees(v), 6)
                                  for k, v in sorted(d.items())},
                    "root_m": [round(r[0], 4), round(r[1], 4)]})
        outputs.append(png)
        log(f"SHOT {name} card={card} f={frame} deg={deg} "
            f"maxdeg={png['max_delta_deg']} bytes={png['bytes']}")

    report = {
        "blender": bpy.app.version_string,
        "source_blend": str(BLEND.relative_to(BAKE)).replace("\\", "/"),
        "source_blend_sha256": blend_sha,
        "table": "baked2.json",
        "table_sha256": hashlib.sha256(TABLE.read_bytes()).hexdigest(),
        "spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "mapping_sha256": hashlib.sha256(MAPPING.read_bytes()).hexdigest(),
        "apose_points": {k: [round(v[0], 5), round(v[1], 5)]
                         for k, v in P.items()},
        "method": "A-pose rest rig + voxel continuous shell + ARMATURE_AUTO "
                  "+ Data Transfer + relative-to-rest incremental drive "
                  "+ same retarget layer as 3D攻击GIF/make_puppet.py",
        "rig": {"bones": len(rig.pose.bones), "names": sorted(rig.pose.bones.keys())},
        "proxy": {"voxel_size": VOXEL, "verts": proxy_v, "faces": proxy_f,
                  "auto_weight_covered": proxy_covered},
        "final": {"verts": len(final.data.vertices),
                  "covered": covered, "coverage": round(covered / len(final.data.vertices), 5),
                  "multi_bone_vertices": multi, "assets": assets},
        "rigid_baseline": {"per_bone": bucket_counts},
        "stance_identity": {"vertices_identical": identical,
                            "tolerance_m": 1e-5,
                            "max_vertex_delta_m": round(max_vertex_delta, 9),
                            "mean_vertex_delta_m": round(mean_vertex_delta, 9),
                            "rest_png": rest_png, "stance_png": stance_png},
        "jab8_ab": {"smooth_tear": tear_smooth, "rigid_tear": tear_rigid,
                    "smooth_displacement": disp_smooth,
                    "rigid_displacement": disp_rigid,
                    "retarget_signals": jab_sig,
                    "jab8_delta_deg": {k: round(math.degrees(v), 6)
                                       for k, v in sorted(jab_delta.items())},
                    "pngs": ab_pngs},
        "shots": outputs,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    (HERE / "c_build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"C_BUILD_OK shots={len(outputs) + 4} elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
