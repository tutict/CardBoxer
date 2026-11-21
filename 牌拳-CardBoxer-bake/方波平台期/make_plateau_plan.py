"""P3 · 生成「候选腿骨映射 × 全量 284 帧」的 Blender 姿态计划。

结构与 P2 的 sweep_plan.json 完全一致，可直接喂给
动作表现P2/tests/sweep_tear_blender.py（它只消费 delta_deg / root_m，
不重算公式）。delta 用 diag_motion.retarget_delta 逐字同公式复算，
只把 4 条腿骨换成候选映射的输出。

档位：
  hard09_baseline —— 现状（P2 上线态，硬 clamp 9°）
  atan09 / atan12 / atan15 —— atan 软限幅，cap 作为渐近上限
  tanh12 —— P2 研究过的 tanh 软压缩，作对照

用法：python make_plateau_plan.py
产出：data/plateau_plan.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
DIAG = BAKE / "动作优化诊断"
P2_PLAN = BAKE / "动作表现P2" / "data" / "sweep_plan.json"
OUT = HERE / "data" / "plateau_plan.json"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")


def hard(x: float, cap: float) -> float:
    return max(-cap, min(cap, x))


def soft_tanh(x: float, cap: float) -> float:
    return cap * math.tanh(x / cap)


def soft_atan(x: float, cap: float) -> float:
    return cap * (2.0 / math.pi) * math.atan((math.pi / 2.0) * x / cap)


CANDIDATES = [
    ("hard09_baseline", "hard", 9.0, hard, "baseline"),
    ("atan09", "atan", 9.0, soft_atan, "candidate"),
    ("atan12", "atan", 12.0, soft_atan, "candidate"),
    ("atan15", "atan", 15.0, soft_atan, "candidate"),
    ("tanh12", "tanh", 12.0, soft_tanh, "research"),
]


def main() -> int:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    tracks = {k: v["track"] for k, v in cm["cards"].items()}
    tracks.update({k: v["track"] for k, v in cm["motions"].items()})
    keys = list(mi["joint_names"])
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    stance_points = make_points(stance_j)
    chain, base = mi["chain"], mi["mapping"]
    px_to_m = float(mi["px_to_m"])
    cfg = dict(base)
    cfg["leg_cap_deg"] = 1e9  # 拿未经 clamp 的原始腿角

    frames = [{"card": c, "frame": i, "why": "all_frames"}
              for c, track in tracks.items() for i in range(len(track))]
    # 每帧只复算一次 retarget，五档共用
    per_frame = []
    for card, track in tracks.items():
        for i, frame in enumerate(track):
            fj = {k: tuple(frame[k]) for k in keys}
            d, raw = retarget_delta(fj, stance_j, chain, cfg,
                                    stance_points)
            dx = (fj["hip"][0] - stance_j["hip"][0]) * px_to_m
            dz = -(fj["hip"][1] - stance_j["hip"][1]) * px_to_m
            per_frame.append((card, i, {n: float(d[n]) for n in d},
                              {n: float(raw[n]) for n in LEG_BONES},
                              [dx, dz]))

    cases, poses = [], []
    for cid, mode, cap, fn, purpose in CANDIDATES:
        cases.append({"id": cid, "leg_cap_deg": cap, "leg_mode": mode,
                      "purpose": purpose, "arm_gain_multiplier": 1.0,
                      "arm_gain_deg": dict(base["arm_gain_deg"])})
        for card, i, d, raw, root in per_frame:
            dd = dict(d)
            for b in LEG_BONES:
                dd[b] = fn(raw[b], cap)
            poses.append({"case": cid, "card": card, "frame": i,
                          "why": "all_frames", "delta_deg": dd,
                          "root_m": root})

    plan = {
        "glb": str(GAME / "assets" / "3d" / "player-rigged.glb"),
        "px_to_m": px_to_m,
        "chain": chain,
        "apose_points": mi["apose_points"],
        "bones": mi["bones"],
        "cases": cases, "poses": poses,
        "frame_count": len(frames), "frames": frames,
        "legend": {
            "delta_deg": "rig_driver.gd::retarget_delta 同公式，单位度",
            "hard": "clamp(raw, -cap, cap)，P2 上线态",
            "atan": "cap*(2/pi)*atan((pi/2)*raw/cap)，初始斜率 1",
            "tanh": "cap*tanh(raw/cap)，P2 研究档",
        },
    }
    OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    p2 = json.loads(P2_PLAN.read_text(encoding="utf-8"))
    rep_pairs = {(f["card"], f["frame"]) for f in p2["frames"]}
    print("CASES", len(cases), "FRAMES", len(frames), "POSES", len(poses))
    print("P2_REPRESENTATIVE_FRAMES", len(rep_pairs))
    all_pairs = {(f["card"], f["frame"]) for f in frames}
    ok = (len(cases) == len(CANDIDATES) and len(frames) == 284
          and len(poses) == len(CANDIDATES) * 284
          and rep_pairs <= all_pairs)
    print("PLATEAU_PLAN_OK" if ok else "PLATEAU_PLAN_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
