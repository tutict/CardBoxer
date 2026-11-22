"""阶段 3：导出 Godot 驱动层的「输入」与 Blender 端「基准」。

分工（这是本方案的关键边界）：
  · motion_input.json  = Godot 运行时真正读的输入：stance + 三卡逐帧
    11 关节 + retarget mapping + 13 骨顺序。GDScript 自己实现
    make_points / angle / retarget_delta / root 位移，不读烘死的动画。
  · rig_frames.json    = Blender 端独立基准：pose_frame 每帧产出的
    delta 角度、matrix_basis 的 quat/loc/scale、global pose translation。
    Godot 侧只拿它做数值校验，不拿来驱动。

用法：blender.exe -b --python export_rig_frames.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
E = BAKE / "route-e-player-3d-rigging"
sys.path.insert(0, str(BAKE / "route-c-real-3d-fix"))
import c_build as C  # noqa: E402

BLEND = E / "player-V4b-deformable-continuous-shell.blend"
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3d-attack-gifs" / "apose_joints.json"
MAPPING = BAKE / "3d-attack-gifs" / "puppet_mapping.json"
OUT_INPUT = HERE / "data" / "motion_input.json"
OUT_FRAMES = HERE / "data" / "rig_frames.json"
CARDS = (("jab", 14), ("cross", 22), ("wave", 36))


def log(*a):
    print(*a, flush=True)


def main() -> int:
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    stance = C.joints_of(table, None, 0)
    P = C.apose_points({"foe": spec["player"]})

    # 1) 运行时输入：只给原始 2D 关节表与 mapping，不给任何烘好的 pose。
    tracks = {}
    for card, n in CARDS:
        src = table["cards"] if card in table["cards"] else table["motions"]
        track = src[card]["track"]
        assert len(track) >= n, (card, len(track), n)
        tracks[card] = [
            {k: [round(float(v[0]), 4), round(float(v[1]), 4)]
             for k, v in C.joints_of(table, card, f).items()}
            for f in range(n)]
    motion = {
        "source": "baked2.json",
        "joint_names": list(C.JOINTS),
        "stance": {k: [round(float(v[0]), 4), round(float(v[1]), 4)]
                   for k, v in stance.items()},
        "cards": {card: {"frames": n, "track": tracks[card]}
                  for card, n in CARDS},
        "mapping": {k: v for k, v in mapping.items()
                    if not k.startswith("_")},
        "bones": [n for n, _p, _u, _v in C.CHAIN],
        "chain": [[n, p, u, v] for n, p, u, v in C.CHAIN],
        "apose_points": {k: [round(float(v[0]), 6), round(float(v[1]), 6)]
                         for k, v in P.items()},
        "px_to_m": 0.01,
    }
    OUT_INPUT.parent.mkdir(parents=True, exist_ok=True)
    OUT_INPUT.write_text(json.dumps(motion, ensure_ascii=False,
                                    separators=(",", ":")) + "\n",
                         encoding="utf-8")

    # 2) Blender 端基准：逐帧 pose_frame 的 delta 与 matrix_basis。
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    rig = next(o for o in bpy.context.scene.objects
               if o.type == "ARMATURE")
    frames = []
    for card, frame in [(None, 0)] + [(c, f) for c, n in CARDS
                                      for f in range(n)]:
        delta, root, signals = C.pose_frame(
            rig, P, table, stance, card, frame, mapping)
        bones = {}
        for name in motion["bones"]:
            pb = rig.pose.bones[name]
            loc, rot, scale = pb.matrix_basis.decompose()
            bones[name] = {
                "delta_deg": round(math.degrees(delta[name]), 5),
                "quat": [round(float(v), 7) for v in
                         (rot.w, rot.x, rot.y, rot.z)],
                "loc": [round(float(v), 7) for v in loc],
                "scale": [round(float(v), 7) for v in scale],
                "global_pos": [round(float(v), 6) for v in
                               pb.matrix.translation],
            }
        frames.append({
            "card": card if card else "stance", "frame": frame,
            "root_m": [round(float(v), 6) for v in root],
            "signals": signals, "bones": bones,
        })
    baseline = {
        "source_blend": str(BLEND),
        "blender": bpy.app.version_string,
        "algorithm": "c_build.pose_frame / retarget_delta",
        "frame_count": len(frames),
        "bones": motion["bones"],
        "frames": frames,
    }
    OUT_FRAMES.write_text(json.dumps(baseline, ensure_ascii=False,
                                     separators=(",", ":")) + "\n",
                          encoding="utf-8")
    log("MOTION_INPUT", OUT_INPUT.stat().st_size, "B")
    log("RIG_FRAMES", OUT_FRAMES.stat().st_size, "B",
        "frames", len(frames))
    assert len(frames) == 1 + sum(n for _c, n in CARDS) == 73
    log("RIG_FRAMES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
