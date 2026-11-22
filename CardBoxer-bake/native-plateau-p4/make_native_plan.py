"""P4 · 生成「候选数据层改法 × 全量 284 帧」的 Blender 姿态计划。

结构与 P3 的 plateau_plan.json 一致，可直接喂给
motion-presentation-p2/tests/sweep_tear_blender.py（只消费 delta_deg / root_m）。

三档：
  baseline  —— 当前 P3 上线态（atan12 + 原动作表），外部对照
  hybrid    —— 长定格段 LERP 过渡 + 残留平台 MICRO 0.3（推荐档）
  micro05   —— 只用 MICRO 0.5，改动最小，作风险对照

同时把推荐档修改后的 11 关节表落到 data/hybrid_tracks.json，
供 apply_native.py 原样写入三份数据层，避免两处各自重算导致分叉。

用法：python make_native_plan.py
产出：data/native_plan.json、data/hybrid_tracks.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DIAG = BAKE / "motion-diagnostics"
OUT = HERE / "data" / "native_plan.json"
TRACKS_OUT = HERE / "data" / "hybrid_tracks.json"
sys.path.insert(0, str(DIAG))
sys.path.insert(0, str(HERE))
from diag_motion import make_points, retarget_delta  # noqa: E402
from evaluate_candidates import (  # noqa: E402
    CAP, EXACT_EPS, LEG_BONES, Ctx, build_lerp, build_micro,
    frame_joints, leg_value, segments_of,
)

CASES = ("baseline", "hybrid", "micro05")


def main() -> int:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    ctx = Ctx(mi)
    tracks = {k: v["track"] for k, v in cm["cards"].items()}
    tracks.update({k: v["track"] for k, v in cm["motions"].items()})
    keys = ctx.keys
    stance_j = ctx.stance
    stance_points = ctx.points
    chain = ctx.chain
    cfg = dict(mi["mapping"])
    cfg["leg_cap_deg"] = 1e9
    px_to_m = float(mi["px_to_m"])

    base = {}
    flags = {}
    hybrid = {}
    micro05 = {}
    changed_frames = {}
    for card, track in tracks.items():
        base[card] = [frame_joints(f, keys) for f in track]
        raws = [ctx.raw(j) for j in base[card]]
        flags[card] = [
            any(abs(raws[i + 1][b] - raws[i][b]) < EXACT_EPS
                for b in LEG_BONES)
            for i in range(len(track) - 1)]
        micro05[card] = build_micro(base[card], flags[card], 0.5)
        lerped = build_lerp(base[card], flags[card])
        raws2 = [ctx.raw(j) for j in lerped]
        flags2 = [
            any(abs(raws2[i + 1][b] - raws2[i][b]) < EXACT_EPS
                for b in LEG_BONES)
            for i in range(len(lerped) - 1)]
        hybrid[card] = build_micro(lerped, flags2, 0.3)
        changed_frames[card] = [
            i for i, (a, b) in enumerate(zip(base[card], hybrid[card]))
            if any(a[k] != b[k] for k in keys)]

    variants = {"baseline": base, "hybrid": hybrid, "micro05": micro05}

    frames = [{"card": c, "frame": i, "why": "all_frames"}
              for c, track in tracks.items() for i in range(len(track))]
    cases, poses = [], []
    for cid in CASES:
        cases.append({"id": cid, "leg_cap_deg": CAP, "leg_mode": "atan",
                      "purpose": ("baseline" if cid == "baseline"
                                  else "candidate"),
                      "arm_gain_multiplier": 1.0,
                      "arm_gain_deg": dict(mi["mapping"]["arm_gain_deg"])})
        for card, track in tracks.items():
            for i in range(len(track)):
                fj = {k: tuple(v) for k, v in
                      variants[cid][card][i].items()}
                d, raw = retarget_delta(fj, stance_j, chain, cfg,
                                        stance_points)
                dd = {n: float(d[n]) for n in d}
                for b in LEG_BONES:
                    dd[b] = leg_value(float(raw[b]))
                dx = (fj["hip"][0] - stance_j["hip"][0]) * px_to_m
                dz = -(fj["hip"][1] - stance_j["hip"][1]) * px_to_m
                poses.append({"case": cid, "card": card, "frame": i,
                              "why": "all_frames", "delta_deg": dd,
                              "root_m": [dx, dz]})

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
            "baseline": "P3 上线态 atan12 + 原动作表",
            "hybrid": "定格段 LERP 过渡 + 残留 MICRO 0.3",
            "micro05": "仅 MICRO 0.5 微扰",
        },
    }
    OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    tracks_out = {
        "source": "card_motion.json + motion_input*.json（三份当前逐值相同）",
        "recommended_case": "hybrid",
        "joints": keys,
        "changed_frames": changed_frames,
        "changed_frame_total": sum(len(v) for v in changed_frames.values()),
        "tracks": {
            card: [{k: [round(float(fr[k][0]), 6),
                        round(float(fr[k][1]), 6)]
                    for k in keys}
                   for fr in hybrid[card]]
            for card in tracks},
    }
    TRACKS_OUT.write_text(
        json.dumps(tracks_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    checks = {
        "three_cases": len(cases) == 3,
        "frames_284": len(frames) == 284,
        "poses_852": len(poses) == 852,
        "tracks_15": len(tracks) == 15,
        "hybrid_changes_some_frames": (
            tracks_out["changed_frame_total"] > 0),
        "hybrid_keeps_frame_counts": all(
            len(v) == len(tracks[c]) for c, v in hybrid.items()),
        "no_nan_in_deltas": all(
            v == v for p in poses for v in p["delta_deg"].values()),
    }
    print("CASES", len(cases), "FRAMES", len(frames), "POSES", len(poses))
    print("HYBRID_CHANGED_FRAMES", tracks_out["changed_frame_total"])
    for k, v in checks.items():
        print("CHECK", k, v)
    ok = all(checks.values())
    print("NATIVE_PLAN_OK" if ok else "NATIVE_PLAN_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
