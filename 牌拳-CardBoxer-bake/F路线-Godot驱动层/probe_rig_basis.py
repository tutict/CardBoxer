"""阶段 1 诊断：Blender 端 pose_frame 产出的骨骼局部变换长什么样。

要回答三个问题，决定 GDScript 驱动层怎么写：
  1. A-pose rest 13 骨在 armature space 的 head/tail 坐标；
  2. 一帧驱动后每根骨的 matrix_basis（loc/quat/scale）形态；
  3. matrix_basis 的旋转轴/角度是否就是 retarget_delta 的 delta。

只读 E 路线交付的 .blend，不回写任何归档。
用法：blender.exe -b --python probe_rig_basis.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
E = BAKE / "E路线-玩家3D绑骨"
sys.path.insert(0, str(BAKE / "C路线-真3D修复"))
import c_build as C  # noqa: E402

BLEND = E / "玩家V4b-可变形连续壳.blend"
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3D攻击GIF" / "apose_joints.json"
MAPPING = BAKE / "3D攻击GIF" / "puppet_mapping.json"
OUT = HERE / "data" / "rig_basis_probe.json"


def q_row(name: str, pb, delta: float) -> dict:
    loc, rot, scale = pb.matrix_basis.decompose()
    axis = rot.axis
    ang = math.degrees(rot.angle)
    return {
        "bone": name,
        "delta_deg": round(math.degrees(delta), 4),
        "loc": [round(v, 6) for v in loc],
        "quat": [round(v, 6) for v in (rot.w, rot.x, rot.y, rot.z)],
        "quat_axis": [round(v, 5) for v in axis],
        "quat_angle_deg": round(ang, 4),
        "scale": [round(v, 6) for v in scale],
        "rest_head": [round(v, 5) for v in pb.bone.head_local],
        "rest_tail": [round(v, 5) for v in pb.bone.tail_local],
        "global_pose_translation": [
            round(v, 6) for v in pb.matrix.translation],
    }


def main() -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    P = C.apose_points({"foe": spec["player"]})
    stance = C.joints_of(table, None, 0)

    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    hi = next(o for o in scene.objects
              if o.type == "MESH"
              and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))
    shell = next(m for m in hi.modifiers
                 if m.type == "SURFACE_DEFORM").target
    print("OPEN", BLEND.name, "rig", rig.name,
          "bones", len(rig.pose.bones),
          "hi_verts", len(hi.data.vertices),
          "shell_verts", len(shell.data.vertices))
    print("SHELL_GROUPS", [g.name for g in shell.vertex_groups])
    print("HI_GROUPS", [g.name for g in hi.vertex_groups])

    frames = []
    for card, frame in ((None, 0), ("jab", 6), ("cross", 10),
                        ("wave", 17)):
        delta, root, signals = C.pose_frame(
            rig, P, table, stance, card, frame, mapping)
        rows = [q_row(n, rig.pose.bones[n], delta[n])
                for n, _p, _u, _v in C.CHAIN]
        frames.append({"card": card, "frame": frame, "root": root,
                       "signals": signals, "bones": rows})
        print("FRAME", card, frame,
              "max_abs_quat_deg",
              round(max(abs(r["quat_angle_deg"]) for r in rows), 3),
              "max_abs_delta_deg",
              round(max(abs(r["delta_deg"]) for r in rows), 3))

    out = {
        "blend": str(BLEND),
        "blend_sha256": hashlib.sha256(BLEND.read_bytes()).hexdigest(),
        "bone_names": [b.name for b in rig.data.bones],
        "hi_verts": len(hi.data.vertices),
        "shell_verts": len(shell.data.vertices),
        "shell_groups": [g.name for g in shell.vertex_groups],
        "hi_groups": [g.name for g in hi.vertex_groups],
        "apose_points": {k: [round(v, 6) for v in p]
                         for k, p in P.items()},
        "frames": frames,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("RIG_BASIS_PROBE_OK", OUT.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
