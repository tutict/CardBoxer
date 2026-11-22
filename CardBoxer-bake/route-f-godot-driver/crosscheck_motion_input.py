"""纯 Python 独立复算：motion_input.json 是否足以重建 retarget_delta。

不 import c_build、不依赖 Blender；算法按公式重写，逐帧逐骨与
rig_frames.json 的 Blender 基准 delta_deg 比对。这份实现同时是
GDScript RigDriver.gd 的算法蓝本。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE / "data" / "motion_crosscheck.json"


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def angle(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])


def wrap_pi(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def clamp(v, cap):
    return max(-cap, min(cap, v))


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


def retarget(frame_j, stance_j, chain, mapping):
    fp, sp = make_points(frame_j), make_points(stance_j)
    raw = {n: math.degrees(wrap_pi(angle(fp[u], fp[v]) -
                                   angle(sp[u], sp[v])))
           for n, _p, u, v in chain}
    torso = math.degrees(wrap_pi(angle(fp["A"], fp["D"]) -
                                 angle(sp["A"], sp["D"])))
    used = clamp(torso * mapping["torso_gain"], mapping["torso_cap_deg"])
    mf = math.dist(frame_j["f_hand"], stance_j["f_hand"])
    mb = math.dist(frame_j["b_hand"], stance_j["b_hand"])
    tf = min(1.0, mf / mapping["reach_norm_px"])
    tb = min(1.0, mb / mapping["reach_norm_px"])
    tw = (min(1.0, min(mf, mb) / mapping["wave_min_norm_px"])
          * mapping["wave_arm_weight"])
    af, ab = max(tf, tw), max(tb, tw)
    g, cap = mapping["arm_gain_deg"], mapping["leg_cap_deg"]
    return {
        "hips": 0.0, "spine": used, "chest": 0.0, "neck": 0.0,
        "head": -used * mapping["head_compensation"],
        "upperarm_f": -g["f_upper"] * af,
        "forearm_f": -g["f_fore"] * af,
        "upperarm_b": g["b_upper"] * ab,
        "forearm_b": g["b_fore"] * ab,
        "thigh_f": clamp(raw["thigh_f"], cap),
        "shin_f": clamp(raw["shin_f"], cap),
        "thigh_b": clamp(raw["thigh_b"], cap),
        "shin_b": clamp(raw["shin_b"], cap),
    }


def main() -> int:
    motion = json.loads((DATA / "motion_input.json").read_text(
        encoding="utf-8"))
    baseline = json.loads((DATA / "rig_frames.json").read_text(
        encoding="utf-8"))
    chain = motion["chain"]
    mapping = motion["mapping"]
    stance = motion["stance"]
    assert len(baseline["frames"]) == 73

    worst = 0.0
    rows = []
    for f in baseline["frames"]:
        card = f["card"]
        if card == "stance":
            frame_j = stance
        else:
            frame_j = motion["cards"][card]["track"][f["frame"]]
        calc = retarget(frame_j, stance, chain, mapping)
        diffs = {n: abs(calc[n] - f["bones"][n]["delta_deg"])
                 for n in motion["bones"]}
        mx = max(diffs.values())
        worst = max(worst, mx)
        rows.append({"card": card, "frame": f["frame"],
                     "max_abs_delta_deg": round(mx, 6)})
        # root 位移也独立复算
        dx = (frame_j["hip"][0] - stance["hip"][0]) * motion["px_to_m"]
        dz = -(frame_j["hip"][1] - stance["hip"][1]) * motion["px_to_m"]
        assert abs(dx - f["root_m"][0]) < 1e-6
        assert abs(dz - f["root_m"][1]) < 1e-6
    ok = worst < 1e-4 and len(rows) == 73
    OUT.write_text(json.dumps({
        "frames": len(rows), "worst_abs_delta_deg": round(worst, 7),
        "tolerance_deg": 1e-4, "root_recomputed": True,
        "ok": ok, "rows": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FRAMES={len(rows)} WORST_ABS_DELTA_DEG={worst:.7f} "
          f"TOL=1e-4 ROOT_OK=True")
    print("MOTION_INPUT_OK" if ok else "MOTION_INPUT_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
