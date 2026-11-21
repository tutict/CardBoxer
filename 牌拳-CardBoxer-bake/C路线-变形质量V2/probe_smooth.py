"""权重邻域平滑 sweep：能不能在不牺牲动作幅度的前提下把边撕裂压下去。

背景：领地修正把跨族权重硬切，撕裂反而涨 1.89 倍。理论上相反的改动
（在 C 路线原始平滑权重上再做一次邻域 Laplacian 平滑）应该让权重梯度
更缓、edge tear 更低。本探针用代表帧做参数扫描，只有数据支持才采用。

独立脚本，不改动 c2_build.py / c2_build.json 的既有证据。
用法：blender.exe -b --python probe_smooth.py
"""
from __future__ import annotations

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
sys.path.insert(0, str(HERE))
import c2_build as C2  # noqa: E402
import c_build as C  # noqa: E402

BLEND = BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3D攻击GIF" / "apose_joints.json"
MAPPING = BAKE / "3D攻击GIF" / "puppet_mapping.json"
REP_FRAMES = (("jab", 6), ("cross", 10), ("wave", 17))
CONFIGS = ((0.0, 0), (0.25, 1), (0.5, 1), (0.5, 2), (0.75, 2))


def log(*a):
    print(*a, flush=True)


def build_adj(obj):
    adj = [[] for _ in range(len(obj.data.vertices))]
    for e in obj.data.edges:
        a, b = e.vertices[0], e.vertices[1]
        adj[a].append(b)
        adj[b].append(a)
    return adj


def read_weights(obj):
    return [{g.group: float(g.weight) for g in v.groups}
            for v in obj.data.vertices]


def smooth(W, adj, lam, iters):
    if iters == 0:
        return W
    cur = W
    for _ in range(iters):
        nxt = []
        for i, wi in enumerate(cur):
            nb = adj[i]
            if not nb:
                nxt.append(dict(wi))
                continue
            acc = {}
            for j in nb:
                for gi, w in cur[j].items():
                    acc[gi] = acc.get(gi, 0.0) + w
            m = len(nb)
            nw = {gi: (1.0 - lam) * wi.get(gi, 0.0)
                  + lam * acc.get(gi, 0.0) / m
                  for gi in set(wi) | set(acc)}
            s = sum(nw.values())
            nxt.append({k: v / s for k, v in nw.items() if v / s > 1e-6}
                       if s > 1e-9 else {})
        cur = nxt
    return cur


def write_weights(obj, W):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    dl = bm.verts.layers.deform.verify()
    for v in bm.verts:
        dv = v[dl]
        for gi in list(dv.keys()):
            del dv[gi]
        for gi, w in W[v.index].items():
            dv[gi] = w
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def main() -> int:
    t0 = time.time()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    base_mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    gain_mapping = copy.deepcopy(base_mapping)
    gain_mapping["arm_gain_deg"] = {
        k: v * C2.ARM_GAIN for k, v in base_mapping["arm_gain_deg"].items()}
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    stance = C.joints_of(table, None, 0)
    P = C.apose_points(spec)

    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    for o in list(scene.objects):
        if o.type == "ARMATURE":
            bpy.data.objects.remove(o, do_unlink=True)
    src.hide_render = True

    arm_data = bpy.data.armatures.new("smooth_rig")
    rig = bpy.data.objects.new("smooth_rig", arm_data)
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

    proxy = C.fresh_copy(src, "smooth_proxy")
    proxy.data.remesh_voxel_size = C.VOXEL
    proxy.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy
    bpy.ops.object.voxel_remesh()
    C.auto_weight(proxy, rig)

    base = C.fresh_copy(src, "smooth_base")
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
    base.modifiers.new("smooth_armature", "ARMATURE").object = rig
    base.hide_render = True

    rest_pos, rest_edges = C.evaluated(base)
    hf, hb, foot = C2.clusters(rest_pos, P)
    hip_z, sh_z = P["hip"][1], P["shoulder"][1]
    segs = C2.segments(P)
    owners = C2.owner_families(base, segs)
    W0 = read_weights(base)
    adj = build_adj(base)
    log(f"BASE verts={len(W0)} edges={len(rest_edges)} "
        f"adj_mean={sum(len(a) for a in adj)/len(adj):.2f}")

    out = []
    for lam, iters in CONFIGS:
        obj = C2.clone(base, f"smooth_{lam}_{iters}")
        W = smooth(W0, adj, lam, iters)
        write_weights(obj, W)
        pur = C2.purity(obj, owners)
        rows = []
        for cid, fr in REP_FRAMES:
            for mtag, mapping in (("base", base_mapping), ("gain", gain_mapping)):
                _d, _r, sig = C.pose_frame(rig, P, table, stance, cid, fr, mapping)
                pos, _ = C.evaluated(obj)
                m = C2.frame_metrics(rest_pos, rest_edges, pos,
                                     hf, hb, foot, hip_z, sh_z)
                rows.append({"card": cid, "frame": fr, "gain": mtag,
                             "tear_p999_m": m["tear_p999_m"],
                             "tear_gt5cm": m["tear_gt5cm"],
                             "reach_max_m": m["reach_max_m"]})
        gain_rows = [r for r in rows if r["gain"] == "gain"]
        rec = {
            "lam": lam, "iters": iters,
            "tear_gain_mean": round(sum(r["tear_p999_m"] for r in gain_rows) / 3, 5),
            "tear_gain_max": max(r["tear_p999_m"] for r in gain_rows),
            "gt5cm_gain_max": max(r["tear_gt5cm"] for r in gain_rows),
            "reach_gain_mean": round(sum(r["reach_max_m"] for r in gain_rows) / 3, 5),
            "purity_arm_f": pur["arm_f"]["mean_own_weight"],
            "purity_torso": pur["torso"]["mean_own_weight"],
            "rows": rows,
        }
        out.append(rec)
        log(f"CFG lam={lam} iters={iters} tear={rec['tear_gain_mean']} "
            f"max={rec['tear_gain_max']} reach={rec['reach_gain_mean']} "
            f"arm_f={rec['purity_arm_f']} elapsed={time.time()-t0:.1f}s")
        bpy.data.objects.remove(obj, do_unlink=True)

    report = {
        "fingerprints": {k: hashlib.sha256(p.read_bytes()).hexdigest()
                         for k, p in (("blend", BLEND), ("table", TABLE),
                                      ("spec", SPEC), ("mapping", MAPPING))},
        "configs": list(CONFIGS), "frames": [list(x) for x in REP_FRAMES],
        "results": out, "elapsed_seconds": round(time.time() - t0, 2),
    }
    (HERE / "smooth_sweep.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log("SMOOTH_SWEEP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
