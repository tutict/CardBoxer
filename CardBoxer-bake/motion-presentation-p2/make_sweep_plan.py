"""P2 阶段二：生成「候选 mapping × 代表帧」的姿态计划（纯 Python，不进 Blender）。

  * delta_deg 用 diag_motion.retarget_delta 复算，与游戏 rig_driver.gd 同公式；
  * leg_mode=hard 是游戏现行 clamp；soft 是 cap*tanh(raw/cap) 的研究对照，
    只在需要改驱动源码时才会被采纳，本计划里只用来量化收益；
  * 代表帧：每条轨道取「腿部原始信号峰值帧」与「手臂信号峰值帧」，
    再加历史 sweep 用过的 jab7 / cross11 / wave18 便于对照。

产出：data/sweep_plan.json（Blender 侧只消费，不重算公式）
用法：python make_sweep_plan.py
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DIAG = BAKE / "motion-diagnostics"
OUT = HERE / "data" / "sweep_plan.json"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
# (id, leg_cap_deg, leg_mode, arm_gain_multiplier, purpose)
CANDIDATES = [
    ("cap03_hard_g100", 3.0, "hard", 1.0, "baseline"),
    ("cap06_hard_g100", 6.0, "hard", 1.0, "candidate"),
    ("cap09_hard_g100", 9.0, "hard", 1.0, "candidate"),
    ("cap12_hard_g100", 12.0, "hard", 1.0, "candidate"),
    ("cap09_hard_g125", 9.0, "hard", 1.25, "candidate"),
    ("cap09_hard_g150", 9.0, "hard", 1.5, "candidate"),
    ("cap12_hard_g125", 12.0, "hard", 1.25, "candidate"),
    ("cap09_soft_g125", 9.0, "soft", 1.25, "research"),
    ("cap09_soft_g150", 9.0, "soft", 1.5, "research"),
    ("cap12_soft_g150", 12.0, "soft", 1.5, "research"),
]
HISTORICAL_FRAMES = (("jab", 7), ("cross", 11), ("wave", 18))


def mapping_for(cap: float, gain_mult: float, base: dict) -> dict:
    m = copy.deepcopy(base)
    # 让 retarget_delta 返回未经 clamp 的原始腿角，之后统一按 mode 处理
    m["leg_cap_deg"] = 1e9
    m["arm_gain_deg"] = {k: v * gain_mult
                         for k, v in base["arm_gain_deg"].items()}
    return m, cap


def leg_value(raw: float, cap: float, mode: str) -> float:
    if mode == "hard":
        return max(-cap, min(cap, raw))
    return cap * math.tanh(raw / cap)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-frames", action="store_true",
                        help="用 15 轨全部 284 帧代替代表帧")
    parser.add_argument("--only", default="",
                        help="逗号分隔的候选 id，默认全部")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    wanted = ([s.strip() for s in args.only.split(",") if s.strip()]
              if args.only else None)
    cand = [c for c in CANDIDATES
            if wanted is None or c[0] in wanted]
    if not cand:
        print("SWEEP_PLAN_FAILED no matching cases")
        return 1
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

    # 代表帧：每轨腿峰 / 臂峰，去重 + 历史三帧；--all-frames 时改全量
    chosen: list[tuple[str, int, str]] = []
    seen = set()
    if args.all_frames:
        for card, track in tracks.items():
            for i in range(len(track)):
                seen.add((card, i))
                chosen.append((card, i, "all_frames"))
    else:
        for card, track in tracks.items():
            leg_scores, arm_scores = [], []
            for i, frame in enumerate(track):
                fj = {k: tuple(frame[k]) for k in keys}
                d, raw = retarget_delta(fj, stance_j, chain, base,
                                        stance_points)
                leg_scores.append(sum(abs(float(raw[n])) for n in LEG_BONES))
                arm_scores.append(max(abs(float(d[n])) for n in
                                      ("upperarm_f", "forearm_f",
                                       "upperarm_b", "forearm_b")))
            lp = max(range(len(track)), key=lambda i: leg_scores[i])
            apk = max(range(len(track)), key=lambda i: arm_scores[i])
            for idx, why in ((lp, "leg_peak"), (apk, "arm_peak")):
                if (card, idx) not in seen:
                    seen.add((card, idx))
                    chosen.append((card, idx, why))
        for card, idx in HISTORICAL_FRAMES:
            if (card, idx) not in seen:
                seen.add((card, idx))
                chosen.append((card, idx, "historical_anchor"))

    cases, poses = [], []
    for cid, cap, mode, gain, purpose in cand:
        cfg, _ = mapping_for(cap, gain, base)
        cases.append({"id": cid, "leg_cap_deg": cap, "leg_mode": mode,
                      "arm_gain_multiplier": gain, "purpose": purpose,
                      "arm_gain_deg": cfg["arm_gain_deg"]})
        for card, idx, why in chosen:
            frame = tracks[card][idx]
            fj = {k: tuple(frame[k]) for k in keys}
            d, raw = retarget_delta(fj, stance_j, chain, cfg,
                                    stance_points)
            dd = {n: float(d[n]) for n in d}
            for n in LEG_BONES:
                dd[n] = leg_value(float(raw[n]), cap, mode)
            dx = (fj["hip"][0] - stance_j["hip"][0]) * px_to_m
            dz = -(fj["hip"][1] - stance_j["hip"][1]) * px_to_m
            poses.append({"case": cid, "card": card, "frame": idx,
                          "why": why, "delta_deg": dd,
                          "root_m": [dx, dz]})

    plan = {
        "glb": str(GAME / "assets" / "3d" / "player-rigged.glb"),
        "px_to_m": px_to_m,
        "chain": chain,
        "apose_points": mi["apose_points"],
        "bones": mi["bones"],
        "cases": cases, "poses": poses,
        "frame_count": len(chosen),
        "frames": [{"card": c, "frame": i, "why": w} for c, i, w in chosen],
        "legend": {
            "delta_deg": "rig_driver.gd::retarget_delta 同公式，单位度",
            "root_m": "[dx, dz]，dz 对应 Blender Z",
            "leg_soft": "cap * tanh(raw / cap)，研究对照，游戏当前未实现",
        },
    }
    Path(args.out).write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("CASES", len(cases), "FRAMES", len(chosen), "POSES", len(poses))
    for c in cases:
        print("CASE", c["id"], c["purpose"])
    if not args.all_frames:
        print("FRAME_LIST", [(c, i, w) for c, i, w in chosen])
    ok = (len(cases) == len(cand) and len(poses)
          == len(cand) * len(chosen) and len(chosen) >= 20)
    print("SWEEP_PLAN_OK" if ok else "SWEEP_PLAN_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
