"""Blender headless：在**游戏真实 GLB** 上量「候选 mapping × 代表帧」的边撕裂。

驱动链逐字复刻 rig_driver.gd::apply_frame：
  * 关节点 hv 直接读 motion_input.json 的 apose_points（[x, z] 米）；
  * 每根骨绕 hv 做 in-plane 增量旋转 mRotY(delta_deg)，层级累积；
  * 根位移 (dx, 0, dz)；
  * pose matrix = D[name] @ pb.bone.matrix_local（与 C 路线 pose_frame 同）。
Godot 用 Quaternion(Z, -delta)，Blender 用 RotY(+delta)，是同一物理方向。

用法：
  blender.exe -b --factory-startup --python sweep_tear_blender.py -- \
      <sweep_plan.json> <out.json> [limit]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ARM_NAME = "e_apose_rig"
MESH_NAME = "player_HI_skinned"


def m_rot_y(deg: float) -> Matrix:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return Matrix(((c, 0.0, s, 0.0), (0.0, 1.0, 0.0, 0.0),
                   (-s, 0.0, c, 0.0), (0.0, 0.0, 0.0, 1.0)))


def evaluated(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = ev.to_mesh()
    pos = [(ev.matrix_world @ v.co).copy() for v in m.vertices]
    edges = [(e.vertices[0], e.vertices[1]) for e in m.edges]
    ev.to_mesh_clear()
    return pos, edges


def tear_stats(rest, posed, edges) -> dict:
    disp = [posed[i] - rest[i] for i in range(len(rest))]
    ds = sorted((disp[a] - disp[b]).length for a, b in edges)
    n = len(ds)
    return {
        "edges": n,
        "max_edge_tear_m": round(ds[-1], 6),
        "p999_edge_tear_m": round(ds[int(n * 0.999)], 6),
        "p99_edge_tear_m": round(ds[int(n * 0.99)], 6),
        "mean_edge_tear_m": round(sum(ds) / n, 6),
        "edges_gt_2cm": sum(1 for d in ds if d > 0.02),
        "edges_gt_5cm": sum(1 for d in ds if d > 0.05),
        "max_displacement_m": round(max(v.length for v in disp), 6),
    }


def reset_pose(arm) -> None:
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def apply_pose(arm, chain, apose, delta, root):
    reset_pose(arm)
    base = Matrix.Translation(Vector((root[0], 0.0, root[1])))
    cum, expect = {}, {}
    for e in chain:
        name, parent = e[0], e[1]
        u = e[2]
        hv = Vector((float(apose[u][0]), 0.0, float(apose[u][1])))
        local = (Matrix.Translation(hv) @ m_rot_y(float(delta[name]))
                 @ Matrix.Translation(-hv))
        d = (base if parent is None else cum[parent]) @ local
        cum[name] = d
        want = d @ arm.pose.bones[name].bone.matrix_local
        arm.pose.bones[name].matrix = want
        expect[name] = want
        bpy.context.view_layer.update()
    worst = 0.0
    for name, want in expect.items():
        got = arm.pose.bones[name].matrix
        for r in range(4):
            for c in range(4):
                worst = max(worst, abs(got[r][c] - want[r][c]))
    return worst


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    plan_path, out_path = Path(argv[0]), Path(argv[1])
    limit = int(argv[2]) if len(argv) > 2 else 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=plan["glb"])
    arm = bpy.data.objects[ARM_NAME]
    mesh = bpy.data.objects[MESH_NAME]
    missing = [e[0] for e in plan["chain"] if e[0] not in arm.pose.bones]
    if missing:
        raise RuntimeError("missing bones: %r" % missing)

    reset_pose(arm)
    rest, edges = evaluated(mesh)
    poses = plan["poses"] if limit <= 0 else plan["poses"][:limit]
    rows, t0 = [], time.perf_counter()
    for i, p in enumerate(poses):
        worst = apply_pose(arm, plan["chain"], plan["apose_points"],
                           p["delta_deg"], p["root_m"])
        posed, _ = evaluated(mesh)
        st = tear_stats(rest, posed, edges)
        st.update({"case": p["case"], "card": p["card"],
                   "frame": p["frame"], "why": p["why"],
                   "max_delta_deg": round(max(abs(v) for v in
                                              p["delta_deg"].values()), 4),
                   "leg_peak_deg": round(max(abs(p["delta_deg"][n]) for n in
                                             ("thigh_f", "shin_f",
                                              "thigh_b", "shin_b")), 4),
                   "pose_matrix_max_err": round(worst, 9)})
        rows.append(st)
        if (i + 1) % 25 == 0 or i + 1 == len(poses):
            print("PROGRESS %d/%d elapsed=%.1fs" %
                  (i + 1, len(poses), time.perf_counter() - t0), flush=True)

    result = {
        "blender": bpy.app.version_string,
        "glb": plan["glb"],
        "vertices": len(rest), "edges": len(edges),
        "armature_bones": len(arm.pose.bones),
        "chain_bones": len(plan["chain"]),
        "missing_bones": missing,
        "cases": plan["cases"], "frames": plan["frames"],
        "poses_total_in_plan": len(plan["poses"]),
        "poses_evaluated": len(rows),
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "max_pose_matrix_err": max(r["pose_matrix_max_err"] for r in rows),
        "rows": rows,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n",
                        encoding="utf-8")
    print("TEAR_SWEEP_BLENDER_OK rows=%d edges=%d max_pose_err=%g"
          % (len(rows), len(edges), result["max_pose_matrix_err"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
