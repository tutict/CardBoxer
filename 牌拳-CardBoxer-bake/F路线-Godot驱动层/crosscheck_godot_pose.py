"""纯 Python 独立复算：Godot 运行时驱动层是否与 Blender 端数学等价。

三重对账，任一超差即判失败：
  ① delta_deg      : GDScript 现算 vs rig_frames.json 的 Blender 基准
  ② calc vs engine : GDScript 自算 global origin vs Godot 引擎读回 global pose
  ③ engine vs base : Godot 引擎读回 vs Blender global_pos（坐标映射 x,z,-y）

另外两条承重判据：
  ④ neutral_bone 驱动前后 pose 完全不变（其初值不是 identity，是一个
     -90° X 旋转；第一版拿 identity 当基准，误报过一次）。
  ⑤ pose_readback 逐帧随驱动变化，证明不是「只算不写」。

坐标口径由 data/godot_rig_probe.json 实测：
  Godot (X,Y,Z) = Blender (x, z, -y)，即 export_yup=True 的 Z-up -> Y-up。

不 import Blender/c_build，不依赖 Godot，只读 JSON 独立算。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DRIVE = DATA / "godot_drive_probe.json"
BASELINE = DATA / "rig_frames.json"
RIG = DATA / "godot_rig_probe.json"
OUT = DATA / "godot_pose_crosscheck.json"

TOL_DEG = 1e-4
TOL_M = 2e-4       # 6 位小数 JSON + float32 骨骼矩阵，实测余量见报告


def mapped(bpos):
    """Blender [x,y,z] -> Godot [x,z,-y]."""
    return [bpos[0], bpos[2], -bpos[1]]


def max_abs(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def main() -> int:
    drive = json.loads(DRIVE.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    rig = json.loads(RIG.read_text(encoding="utf-8"))
    result = drive["result"]
    frames = result["frames"]
    base_frames = baseline["frames"]
    assert drive["ok"] is True
    assert len(frames) == len(base_frames) == 73
    assert rig["ok"] is True

    bones = result["bones"]
    worst_delta = 0.0
    worst_calc_engine = 0.0
    worst_engine_base = 0.0
    rows = []
    for got, ref in zip(frames, base_frames):
        assert got["card"] == ref["card"], (got["card"], ref["card"])
        assert got["frame"] == ref["frame"]
        d_delta = max(abs(got["delta_deg"][n] - ref["bones"][n]["delta_deg"])
                      for n in bones)
        d_ce = max(max_abs(got["calc_global_origin"][n],
                           got["engine_global_origin"][n]) for n in bones)
        d_eb = max(max_abs(got["engine_global_origin"][n],
                           mapped(ref["bones"][n]["global_pos"]))
                   for n in bones)
        worst_delta = max(worst_delta, d_delta)
        worst_calc_engine = max(worst_calc_engine, d_ce)
        worst_engine_base = max(worst_engine_base, d_eb)
        rows.append({"card": got["card"], "frame": got["frame"],
                     "delta_deg": round(d_delta, 7),
                     "calc_vs_engine_m": round(d_ce, 7),
                     "engine_vs_blender_m": round(d_eb, 7)})

    worst_root = max(max_abs(g["root_m"], r["root_m"])
                     for g, r in zip(frames, base_frames))

    # neutral_bone：驱动前后 must be identical（不是 identity）。
    ns, ne = result["neutral_start"], result["neutral_end"]
    neutral_ok = (len(ns) == 10 and ns == ne
                  and abs(ns[0] - 0.707107) < 1e-5
                  and abs(ns[1] + 0.707107) < 1e-5)
    neutral_matches_import = (len(ns) == 10
                              and max_abs(ns[:4],
                                          rig["rig"]["bones"][13]["pose_rotation"])
                              < 1e-5
                              and max_abs(ns[4:7],
                                          rig["rig"]["bones"][13]["pose_position"])
                              < 1e-5)

    # pose_readback：每张卡挑 |delta| 最大的那一帧与 stance 比。
    # 不能挑卡的第 0 帧——三卡首帧 delta 全是 0（动作起始），
    # 拿它比 stance 只会误报「没写进去」。
    def pose_of(i):
        return [v for n in bones for v in frames[i]["pose_readback"][n]]
    stance_pose = pose_of(0)
    pick = {}
    for card in ("jab", "cross", "wave"):
        candidates = [(i, f) for i, f in enumerate(frames)
                      if f["card"] == card]
        i, _f = max(candidates, key=lambda t: max(
            abs(v) for v in t[1]["delta_deg"].values()))
        pick[card] = i
    changed = {c: max_abs(stance_pose, pose_of(i)) > 1e-4
               for c, i in pick.items()}
    all_cards_changed = (len(changed) == 3 and all(changed.values()))
    # 写入即读回：每骨 pose_readback 长度 = quat4 + pos3
    readback_shape_ok = all(len(frames[i]["pose_readback"][n]) == 7
                            for i in range(len(frames)) for n in bones)

    checks = {
        "frame_count_73": len(frames) == 73,
        "frames_applied_73": result["frames_applied"] == 73,
        "bone_count_14": result["bone_count"] == 14,
        "bones_driven_13": len(bones) == 13,
        "delta_matches_blender": worst_delta < TOL_DEG,
        "calc_matches_engine": worst_calc_engine < TOL_M,
        "engine_matches_blender": worst_engine_base < TOL_M,
        "root_matches_blender": worst_root < TOL_M,
        "neutral_bone_untouched": neutral_ok,
        "neutral_matches_import": neutral_matches_import,
        "pose_actually_written": all_cards_changed,
        "pose_readback_shape": readback_shape_ok,
        "windowed_render": drive["probe"]["has_opengl"] is True
                           and drive["probe"]["headless"] is False,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "tolerances": {"deg": TOL_DEG, "m": TOL_M},
        "worst": {
            "delta_deg": round(worst_delta, 7),
            "calc_vs_engine_m": round(worst_calc_engine, 7),
            "engine_vs_blender_m": round(worst_engine_base, 7),
            "root_m": round(worst_root, 7),
        },
        "cards_pose_changed": changed,
        "neutral_start": ns,
        "neutral_end": ne,
        "checks": checks,
        "frames": len(rows),
        "rows": rows,
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"WORST delta={worst_delta:.7f}deg "
          f"calc_vs_engine={worst_calc_engine:.7f}m "
          f"engine_vs_blender={worst_engine_base:.7f}m "
          f"root={worst_root:.7f}m")
    print("GODOT_POSE_CROSSCHECK_OK" if ok else "GODOT_POSE_CROSSCHECK_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
