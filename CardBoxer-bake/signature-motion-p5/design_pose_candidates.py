# -*- coding: utf-8 -*-
"""#215 候选姿态设计 + 双侧成本扫描（纯读盘 + 纯计算，不落地）。

只改三条牌型轨（wave / cross / jab）的四个手臂关节，且**端点帧 0 / 末帧
一律不动**（pose_probe.gd 1.5px 红线，P4 端点保护纪律）。
腿关节、非关节元数据、mapping、帧数、序列化格式一律不变。

产出：
  data/candidate_scan.json        三档全量指标
  data/recommended_tracks.json    推荐档 11 关节表（供 #216 三表同步落地）
  data/pose_plan.json             baseline + recommended 全量 284 帧 Blender 计划
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pose_cost as pc  # noqa: E402
import pose_metrics as pm  # noqa: E402

CM = pc.load(pc.CM_PATH)
BASE = pc.tracks_of(CM)
STANCE = pc.joints_of(CM["stance"])
STANCE_RAW = CM["stance"]
INPUTS = pc.inputs()
OUT = HERE / "data"

HAND_JOINTS = ("f_hand", "f_elbow", "b_hand", "b_elbow")
ARM = ("f_hand", "f_elbow")

# 牌型三档的相位边界（从表里的 phase 字段实测，不写死猜测）
PHASES = {
    card: [str(f.get("phase", "react")) for f in track]
    for card, track in BASE.items()
}


def bell(i: int, start: int, peak: int, end: int) -> float:
    """端点为 0、peak 为 1 的分段余弦钟形；区间外恒 0。"""
    if i <= start or i >= end or peak <= start or peak >= end:
        return 0.0
    if i <= peak:
        return 0.5 - 0.5 * math.cos(math.pi * (i - start) / (peak - start))
    return 0.5 + 0.5 * math.cos(math.pi * (i - peak) / (end - peak))


def shift(frame: dict, name: str, dx: float, dy: float) -> None:
    x, y = frame[name]
    frame[name] = [round(float(x) + dx, 6), round(float(y) + dy, 6)]


def build_variant(p: dict) -> tuple[dict, dict]:
    """返回 (新 15 轨 11 关节表, changed_frames)。"""
    out = copy.deepcopy(BASE)
    changed: dict = {}

    # ---- wave：active 段双手前推，恢复「最大牌最有力」-----------------------
    tr = out["wave"]  # 36 帧：windup 0-9 / active 10-17 / recover 18-35
    for i in range(1, len(tr) - 1):
        w = bell(i, 8, 14, 34)
        if w == 0.0:
            continue
        push = p["wave_push"] * w
        # 前手走弧线：向前的同时轻微上抬，避免纯直线
        shift(tr[i], "f_hand", push, -0.10 * push * (1.0 - w))
        shift(tr[i], "f_elbow", 0.40 * push, -0.04 * push * (1.0 - w))
        back = p["wave_push"] * p["wave_two_hand"] * w
        shift(tr[i], "b_hand", back, -0.06 * back)
        shift(tr[i], "b_elbow", 0.40 * back, -0.02 * back)
    changed["wave"] = [i for i, (a, b) in enumerate(zip(BASE["wave"], tr))
                       if any(a[k] != b[k] for k in pc.JOINTS)]

    # ---- jab：轻拳收短，不再完全伸直 -----------------------------------------
    tr = out["jab"]  # 14 帧：windup 0-3 / active 4-6 / recover 7-13
    for i in range(1, len(tr) - 1):
        w = bell(i, 2, 6, 12)
        if w == 0.0:
            continue
        pull = p["jab_pull"] * w
        shift(tr[i], "f_hand", -pull, 0.04 * pull)
        shift(tr[i], "f_elbow", -0.40 * pull, 0.02 * pull)
    changed["jab"] = [i for i, (a, b) in enumerate(zip(BASE["jab"], tr))
                      if any(a[k] != b[k] for k in pc.JOINTS)]

    # ---- cross：蓄力后收 + active 段前推，把峰值从 windup 搬进命中窗 --------
    tr = out["cross"]  # 22 帧：windup 0-5 / active 6-9 / recover 10-21
    for i in range(1, len(tr) - 1):
        rec = p["cross_recoil"] * bell(i, 0, 4, 6)
        fwd = p["cross_push"] * bell(i, 6, 8, 20)
        d = fwd - rec
        if abs(d) < 1e-9:
            continue
        shift(tr[i], "f_hand", d, 0.05 * abs(d))
        shift(tr[i], "f_elbow", 0.40 * d, 0.02 * abs(d))
    changed["cross"] = [i for i, (a, b) in enumerate(zip(BASE["cross"], tr))
                        if any(a[k] != b[k] for k in pc.JOINTS)]
    return out, changed


def endpoint_drift(tracks: dict) -> tuple[float, str]:
    """pose_probe.gd::_gap 口径，逐轨首帧 / 末帧对 stance。"""
    worst, who = 0.0, "none"
    for card, track in tracks.items():
        for label, idx in (("frame0", 0), ("last", len(track) - 1)):
            g = pc.chebyshev_gap(track[idx], STANCE_RAW)
            if g > worst:
                worst, who = g, f"{card} {label}"
    return round(worst, 4), who


def max_2d_shift(tracks: dict) -> tuple[float, str]:
    """相对 P4 基线，逐坐标绝对差的最大值。"""
    worst, who = 0.0, "none"
    for card, track in tracks.items():
        for i, (a, b) in enumerate(zip(BASE[card], track)):
            for k in pc.JOINTS:
                g = max(abs(float(a[k][0]) - float(b[k][0])),
                        abs(float(a[k][1]) - float(b[k][1])))
                if g > worst:
                    worst, who = g, f"{card}:{i}:{k}"
    return round(worst, 4), who


def max_3d_delta_diff(tracks: dict) -> tuple[float, str]:
    worst, who = 0.0, "none"
    for card, track in tracks.items():
        for i, (a, b) in enumerate(zip(BASE[card], track)):
            if all(a[k] == b[k] for k in pc.JOINTS):
                continue
            da = pc.delta_and_root(pc.joints_of(a))[0]
            db = pc.delta_and_root(pc.joints_of(b))[0]
            for bone in da:
                diff = abs(da[bone] - db[bone])
                if diff > worst:
                    worst, who = diff, f"{card}:{i}:{bone}"
    return round(worst, 6), who


def exact_holds(tracks: dict) -> int:
    n = 0
    for track in tracks.values():
        j = [pc.joints_of(f) for f in track]
        n += sum(1 for i in range(1, len(j)) if j[i] == j[i - 1])
    return n


def peak_pair_min(cm_like: dict) -> tuple[float, str]:
    attacks = [c for c in BASE if "active" in PHASES[c]]
    vals = []
    for i, a in enumerate(attacks):
        for b in attacks[i + 1:]:
            vals.append((pm.peak_pose_distance(cm_like, a, b), f"{a}|{b}"))
    return min(vals) if vals else (0.0, "none")


def evaluate(name: str, p: dict) -> dict:
    tracks, changed = build_variant(p)
    cm_like = {"cards": {k: {"track": v} for k, v in tracks.items()
                         if k in CM["cards"]},
               "motions": {k: {"track": v} for k, v in tracks.items()
                           if k in CM["motions"]},
               "stance": STANCE_RAW}
    met = {}
    for card, track in tracks.items():
        met[card] = pm.metrics(track, STANCE, card)
    tier = {c: met[c]["peak_reach_gain_px"] for c in ("wave", "cross", "jab")}
    ordered = tier["wave"] > tier["cross"] > tier["jab"]
    drift, drift_who = endpoint_drift(tracks)
    sh2, sh2_who = max_2d_shift(tracks)
    sh3, sh3_who = max_3d_delta_diff(tracks)
    holds = exact_holds(tracks)
    pair_min, pair_who = peak_pair_min(cm_like)
    attacks = [c for c in BASE if "active" in PHASES[c]]
    active_ok = all(met[c]["peak_reach_phase"] == "active" for c in attacks)
    overshoot = {c: met[c]["recover_overshoot_px"] for c in attacks}

    checks = {
        "three_tiers_strictly_decreasing": ordered,
        "all_attack_peaks_in_active": active_ok,
        "cross_peak_in_active": met["cross"]["peak_reach_phase"] == "active",
        "cross_windup_recoil_nonzero": met["cross"]["windup_recoil_px"] > 0,
        "exact_hold_pairs_zero": holds == 0,
        "endpoint_drift_within_1_5": drift <= 1.5,
        "l8_peak_pair_min_within_80pct": pair_min >= 92.0107 * 0.8,
        "frame_counts_unchanged": all(
            len(tracks[c]) == len(BASE[c]) for c in BASE),
        "endpoints_byte_identical": all(
            tracks[c][0] == BASE[c][0]
            and tracks[c][-1] == BASE[c][-1] for c in BASE),
        "legs_and_metadata_untouched": all(
            all(tracks[c][i][k] == BASE[c][i][k]
                for k in pc.JOINTS if k not in HAND_JOINTS)
            and all(tracks[c][i][m] == BASE[c][i][m]
                    for m in BASE[c][i] if m not in pc.JOINTS)
            for c in BASE for i in range(len(BASE[c]))),
    }
    return {
        "name": name, "params": p, "checks": checks,
        "passed": all(checks.values()),
        "tier_reach_gain_px": {k: round(v, 4) for k, v in tier.items()},
        "tier_bbox_gain_pct": {c: met[c]["peak_bbox_gain_pct"]
                               for c in ("wave", "cross", "jab")},
        "cross_peak": {"frame": met["cross"]["peak_reach_argmax"],
                       "phase": met["cross"]["peak_reach_phase"],
                       "gain": met["cross"]["peak_reach_gain_px"]},
        "wave_peak": {"frame": met["wave"]["peak_reach_argmax"],
                      "phase": met["wave"]["peak_reach_phase"],
                      "gain": met["wave"]["peak_reach_gain_px"]},
        "cross_windup_recoil_px": met["cross"]["windup_recoil_px"],
        "cross_arc_deviation_px": met["cross"]["arc_deviation_px"],
        "exact_hold_pairs": holds,
        "endpoint_drift_px": drift, "endpoint_drift_at": drift_who,
        "max_2d_shift_px": sh2, "max_2d_shift_at": sh2_who,
        "max_3d_delta_diff_deg": sh3, "max_3d_delta_diff_at": sh3_who,
        "l8_peak_pair_min": pair_min, "l8_peak_pair_at": pair_who,
        "attack_overshoot_px": overshoot,
        "changed_frames": {k: len(v) for k, v in changed.items()},
        "changed_frame_total": sum(len(v) for v in changed.values()),
        "_tracks": tracks,
        "_changed": changed,
    }


CASES = {
    "conservative": dict(wave_push=18.0, wave_two_hand=0.0, jab_pull=26.0,
                         cross_recoil=6.0, cross_push=8.0),
    "balanced": dict(wave_push=30.0, wave_two_hand=0.0, jab_pull=32.0,
                     cross_recoil=10.0, cross_push=14.0),
    "bold": dict(wave_push=42.0, wave_two_hand=0.6, jab_pull=36.0,
                 cross_recoil=14.0, cross_push=20.0),
}


def make_plan(tracks: dict) -> dict:
    """baseline + recommended，全量 284 帧，喂 sweep_tear_blender.py。"""
    frames = [{"card": c, "frame": i, "why": "all_frames"}
              for c, tr in BASE.items() for i in range(len(tr))]
    variants = {"baseline": BASE, "pose_p5": tracks}
    cases, poses = [], []
    for cid, variant in variants.items():
        cases.append({
            "id": cid, "leg_cap_deg": INPUTS["cap"],
            "leg_mode": INPUTS["mode"],
            "purpose": "baseline" if cid == "baseline" else "candidate",
            "arm_gain_multiplier": 1.0,
            "arm_gain_deg": dict(INPUTS["arm_gain_deg"]),
        })
        for card, track in variant.items():
            for i, fr in enumerate(track):
                dd, root = pc.delta_and_root(pc.joints_of(fr))
                poses.append({"case": cid, "card": card, "frame": i,
                              "why": "all_frames", "delta_deg": dd,
                              "root_m": root})
    return {
        "glb": str(pc.GAME / "assets" / "3d" / "player-rigged.glb"),
        "px_to_m": INPUTS["px_to_m"],
        "chain": INPUTS["chain"],
        "apose_points": INPUTS["apose_points"],
        "bones": INPUTS["bones"],
        "cases": cases, "poses": poses,
        "frame_count": len(frames), "frames": frames,
        "legend": {
            "delta_deg": "rig_driver.gd::retarget_delta 同公式，单位度",
            "baseline": "P4 上线态（atan12 + micro2 数据层）",
            "pose_p5": "P5 推荐档姿态语言改动（仅 wave/cross/jab 四臂关节）",
        },
    }


def main() -> int:
    results = [evaluate(name, p) for name, p in CASES.items()]
    public = [{k: v for k, v in r.items() if not k.startswith("_")}
              for r in results]
    ok = [r for r in results if r["passed"]]
    # 推荐规则：全硬约束通过 → 选 3D delta 成本最小（双侧里更贵的一侧）
    pick = min(ok, key=lambda r: r["max_3d_delta_diff_deg"]) if ok else None
    scan = {
        "source": str(pc.CM_PATH),
        "baseline_track_count": len(BASE),
        "baseline_frame_total": sum(len(t) for t in BASE.values()),
        "attacks": [c for c in BASE if "active" in PHASES[c]],
        "cases": public,
        "recommended": pick["name"] if pick else None,
        "selection_rule": "所有硬约束通过者中，max_3d_delta_diff_deg 最小",
    }
    (OUT / "candidate_scan.json").write_text(
        json.dumps(scan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print("== 候选扫描（端点帧 0 / 末帧不动，只改四臂关节） ==")
    for r in results:
        print(f"\n[{r['name']}] passed={r['passed']} "
              f"changed={r['changed_frame_total']} 帧")
        print("  tier  wave %.3f / cross %.3f / jab %.3f  ordered=%s"
              % (r["tier_reach_gain_px"]["wave"],
                 r["tier_reach_gain_px"]["cross"],
                 r["tier_reach_gain_px"]["jab"],
                 r["checks"]["three_tiers_strictly_decreasing"]))
        print("  cross peak @%d %s  recoil=%.3f  arc=%.3f"
              % (r["cross_peak"]["frame"], r["cross_peak"]["phase"],
                 r["cross_windup_recoil_px"], r["cross_arc_deviation_px"]))
        print("  holds=%d drift=%.4f(%s) 2D=%.3f(%s) 3D=%.4f°(%s)"
              % (r["exact_hold_pairs"], r["endpoint_drift_px"],
                 r["endpoint_drift_at"], r["max_2d_shift_px"],
                 r["max_2d_shift_at"], r["max_3d_delta_diff_deg"],
                 r["max_3d_delta_diff_at"]))
        print("  L8 min pair=%.3f (%s)  checks_failed=%s"
              % (r["l8_peak_pair_min"], r["l8_peak_pair_at"],
                 [k for k, v in r["checks"].items() if not v]))

    if pick is None:
        print("\nNO_CANDIDATE_PASSED")
        return 1
    print("\nRECOMMENDED", pick["name"])

    tracks_out = {
        "source": "P4 上线态 card_motion.json（三份表当前逐值同步）",
        "recommended_case": pick["name"],
        "joints": pc.JOINTS,
        "changed_frames": pick["_changed"],
        "changed_frame_total": pick["changed_frame_total"],
        "tracks": {
            card: [{k: [round(float(fr[k][0]), 6),
                        round(float(fr[k][1]), 6)]
                    for k in pc.JOINTS}
                   for fr in pick["_tracks"][card]]
            for card in BASE},
    }
    (OUT / "recommended_tracks.json").write_text(
        json.dumps(tracks_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    plan = make_plan(pick["_tracks"])
    (OUT / "pose_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("POSE_PLAN_OK cases=%d poses=%d frames=%d"
          % (len(plan["cases"]), len(plan["poses"]), plan["frame_count"]))
    print("POSE_CANDIDATES_OK" if ok else "POSE_CANDIDATES_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
