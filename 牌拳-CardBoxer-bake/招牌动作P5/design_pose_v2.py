# -*- coding: utf-8 -*-
"""#215 定稿候选：按口径订正 R1（mf 主指标）重做姿态设计与双侧成本扫描。

V1（design_pose_candidates.py）用 reach 欧氏距离，被 shoulder 轨迹污染，
三档全未过，负结果留在 logs/design_pose_candidates.out，不删除、不改写。

本版只改三条牌型轨的四个手臂关节，端点帧 0 / 末帧一律不动：
  · cross —— 原来 f_hand 全程恒 (44,-156) 根本没出拳：windup 段后收蓄力，
             active 段真正前伸，把 mf 峰值搬进命中窗。
  · wave  —— 原来手与肩同步平移：给 f_hand/b_hand 额外前推，变成推掌。
  · jab   —— 轻拳收短，不再完全伸直。

产出 data/candidate_scan.json / recommended_tracks.json / pose_plan.json。
纯读盘 + 纯计算，不落地任何游戏文件。
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pose_axes as pa  # noqa: E402
import pose_cost as pc  # noqa: E402
import pose_metrics as pm  # noqa: E402

CM = pc.load(pc.CM_PATH)
BASE = pc.tracks_of(CM)
STANCE = pc.joints_of(CM["stance"])
STANCE_RAW = CM["stance"]
INPUTS = pc.inputs()
OUT = HERE / "data"

HAND_JOINTS = ("f_hand", "f_elbow", "b_hand", "b_elbow")
PHASES = {c: [str(f.get("phase", "react")) for f in t]
          for c, t in BASE.items()}
ATTACKS = sorted(c for c in BASE if "active" in PHASES[c])


def bell(i: int, start: int, peak: int, end: int) -> float:
    if i <= start or i >= end or peak <= start or peak >= end:
        return 0.0
    if i <= peak:
        return 0.5 - 0.5 * math.cos(math.pi * (i - start) / (peak - start))
    return 0.5 + 0.5 * math.cos(math.pi * (i - peak) / (end - peak))


def shift(frame: dict, name: str, dx: float, dy: float) -> None:
    x, y = frame[name]
    frame[name] = [round(float(x) + dx, 6), round(float(y) + dy, 6)]


def build_variant(p: dict) -> tuple[dict, dict]:
    out = copy.deepcopy(BASE)
    changed: dict = {}

    # ---- wave：双手推掌（额外前推，不再只是整体平移）-----------------------
    tr = out["wave"]
    for i in range(1, len(tr) - 1):
        w = bell(i, 9, 15, 33)
        if w == 0.0:
            continue
        push = p["wave_push"] * w
        dy = -0.10 * push * (1.0 - w)   # 非线性 → 弧线
        shift(tr[i], "f_hand", push, dy)
        shift(tr[i], "f_elbow", 0.35 * push, 0.35 * dy)
        back = push * p["wave_two_hand"]
        shift(tr[i], "b_hand", back, -0.05 * back * (1.0 - w))
        shift(tr[i], "b_elbow", 0.35 * back, 0.0)
    changed["wave"] = [i for i, (a, b) in enumerate(zip(BASE["wave"], tr))
                       if any(a[k] != b[k] for k in pc.JOINTS)]

    # ---- jab：轻拳按「相对站架前伸量」比例收短（保形缩放）-------------------
    # 钟形绝对收短会让原表 frame6/7 同手位的后一帧反而更靠前，
    # 把 mf 峰值推到 recover；比例缩放保持原时间曲线形状，
    # 且端点帧本来就等于 stance，天然零改动。
    tr = out["jab"]
    r = p["jab_ratio"]
    for i in range(1, len(tr) - 1):
        for name in ("f_hand", "f_elbow"):
            x, y = tr[i][name]
            bx = float(STANCE_RAW[name][0])
            by = float(STANCE_RAW[name][1])
            tr[i][name] = [round(bx + (float(x) - bx) * (1.0 - r), 6),
                           round(by + (float(y) - by) * (1.0 - r), 6)]
    changed["jab"] = [i for i, (a, b) in enumerate(zip(BASE["jab"], tr))
                      if any(a[k] != b[k] for k in pc.JOINTS)]

    # ---- cross：蓄力后收 + active 真出拳 -------------------------------------
    tr = out["cross"]
    for i in range(1, len(tr) - 1):
        wr = bell(i, 0, 4, 6)
        wf = bell(i, 5, 8, 20)
        d = p["cross_push"] * wf - p["cross_recoil"] * wr
        if abs(d) < 1e-9:
            continue
        w = max(wr, wf)
        dy = -0.08 * d * (1.0 - w)
        shift(tr[i], "f_hand", d, dy)
        shift(tr[i], "f_elbow", 0.35 * d, 0.35 * dy)
    changed["cross"] = [i for i, (a, b) in enumerate(zip(BASE["cross"], tr))
                        if any(a[k] != b[k] for k in pc.JOINTS)]
    return out, changed


def endpoint_drift(tracks: dict) -> tuple[float, str]:
    worst, who = 0.0, "none"
    for card, track in tracks.items():
        for label, idx in (("frame0", 0), ("last", len(track) - 1)):
            g = pc.chebyshev_gap(track[idx], STANCE_RAW)
            if g > worst:
                worst, who = g, f"{card} {label}"
    return round(worst, 4), who


def max_2d_shift(tracks: dict) -> tuple[float, str]:
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
    vals = [(pm.peak_pose_distance(cm_like, a, b), f"{a}|{b}")
            for i, a in enumerate(ATTACKS) for b in ATTACKS[i + 1:]]
    return min(vals) if vals else (0.0, "none")


def evaluate(name: str, p: dict) -> dict:
    tracks, changed = build_variant(p)
    cm_like = {"cards": {k: {"track": v} for k, v in tracks.items()
                         if k in CM["cards"]},
               "motions": {k: {"track": v} for k, v in tracks.items()
                           if k in CM["motions"]},
               "stance": STANCE_RAW}
    axes = {c: pa.axis_metrics(tracks[c], STANCE_RAW) for c in BASE}
    met = {c: pm.metrics(tracks[c], STANCE, c) for c in BASE}
    tier = {c: axes[c]["mf_peak_px"] for c in ("wave", "cross", "jab")}
    # R2 目标：不再要求三档 mf 递减（那会逼着削 jab，与 reach_probe 冲突）。
    # 改成「把两条本来没驱动的手真正驱动起来」，jab 保持原样。
    wave_strong = tier["wave"] >= 55.0
    cross_strong = tier["cross"] >= 25.0
    wave_over_cross = tier["wave"] >= tier["cross"] + 5.0
    jab_untouched = all(
        BASE["jab"][i][k] == tracks["jab"][i][k]
        for i in range(len(BASE["jab"])) for k in pc.JOINTS)
    active_ok = all(axes[c]["mf_peak_phase"] == "active" for c in ATTACKS)
    drift, drift_who = endpoint_drift(tracks)
    sh2, sh2_who = max_2d_shift(tracks)
    sh3, sh3_who = max_3d_delta_diff(tracks)
    holds = exact_holds(tracks)
    pair_min, pair_who = peak_pair_min(cm_like)

    checks = {
        "wave_arm_drive_strong": wave_strong,
        "cross_arm_drive_strong": cross_strong,
        "wave_stronger_than_cross": wave_over_cross,
        "jab_byte_identical_for_reach_probe": jab_untouched,
        "all_attack_mf_peaks_in_active": active_ok,
        "cross_mf_peak_in_active": axes["cross"]["mf_peak_phase"] == "active",
        "cross_windup_recoil_nonzero": met["cross"]["windup_recoil_px"] > 0,
        "wave_is_push_not_translation": (
            axes["wave"]["mf_peak_px"] >= 40.0
            and axes["wave"]["mf_peak_phase"] == "active"),
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
        "tier_mf_peak_px": {k: round(v, 4) for k, v in tier.items()},
        "tier_mf_peak_frame": {c: axes[c]["mf_peak_frame"]
                               for c in ("wave", "cross", "jab")},
        "tier_mf_peak_phase": {c: axes[c]["mf_peak_phase"]
                               for c in ("wave", "cross", "jab")},
        "tier_forward_ext_gain_px": {
            c: axes[c]["forward_ext_gain_px"] for c in ("wave", "cross", "jab")},
        "baseline_mf_peak_px": {
            c: round(pa.axis_metrics(BASE[c], STANCE_RAW)["mf_peak_px"], 4)
            for c in ("wave", "cross", "jab")},
        "attack_mf_peak_phase": {c: axes[c]["mf_peak_phase"] for c in ATTACKS},
        "cross_windup_recoil_px": met["cross"]["windup_recoil_px"],
        "cross_arc_deviation_px": met["cross"]["arc_deviation_px"],
        "wave_arc_deviation_px": met["wave"]["arc_deviation_px"],
        "exact_hold_pairs": holds,
        "endpoint_drift_px": drift, "endpoint_drift_at": drift_who,
        "max_2d_shift_px": sh2, "max_2d_shift_at": sh2_who,
        "max_3d_delta_diff_deg": sh3, "max_3d_delta_diff_at": sh3_who,
        "l8_peak_pair_min": pair_min, "l8_peak_pair_at": pair_who,
        "attack_overshoot_px": {c: met[c]["recover_overshoot_px"]
                                for c in ATTACKS},
        "changed_frames": {k: len(v) for k, v in changed.items()},
        "changed_frame_total": sum(len(v) for v in changed.values()),
        "_tracks": tracks, "_changed": changed,
    }


# R2：jab_ratio 一律 0。收短轻拳会让 reach_probe 报「隔空命中 42 px」
# （判定 reach 118 / 画面最远 76），是拿判定一致性换数字排序，已实测否决。
# 轻拳的「轻」由帧数短、收招快表达，不由手伸多远表达。
CASES = {
    "conservative": dict(wave_push=30.0, wave_two_hand=0.3, jab_ratio=0.0,
                         cross_recoil=10.0, cross_push=26.0),
    "balanced": dict(wave_push=40.0, wave_two_hand=0.5, jab_ratio=0.0,
                     cross_recoil=12.0, cross_push=36.0),
    "bold": dict(wave_push=50.0, wave_two_hand=0.7, jab_ratio=0.0,
                 cross_recoil=16.0, cross_push=46.0),
}


def make_plan(tracks: dict) -> dict:
    frames = [{"card": c, "frame": i, "why": "all_frames"}
              for c, tr in BASE.items() for i in range(len(tr))]
    cases, poses = [], []
    for cid, variant in (("baseline", BASE), ("pose_p5", tracks)):
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
            "pose_p5": "P5 R2 推荐姿态（仅 wave/cross 四臂关节，jab 不动）",
        },
    }


def main() -> int:
    results = [evaluate(n, p) for n, p in CASES.items()]
    public = [{k: v for k, v in r.items() if not k.startswith("_")}
              for r in results]
    ok = [r for r in results if r["passed"]]
    pick = min(ok, key=lambda r: r["max_3d_delta_diff_deg"]) if ok else None
    scan = {
        "metric_revision": "R1 + R2（R1：mf 主指标；R2：jab 不动，"
                           "放弃三档递减，改钉 wave/cross 真正驱动）",
        "source": str(pc.CM_PATH),
        "baseline_track_count": len(BASE),
        "baseline_frame_total": sum(len(t) for t in BASE.values()),
        "attacks": ATTACKS,
        "negative_result_v1": "logs/design_pose_candidates.out（reach 口径，三档全未过）",
        "cases": public,
        "recommended": pick["name"] if pick else None,
        "selection_rule": "全部硬约束通过者中 max_3d_delta_diff_deg 最小",
    }
    (OUT / "candidate_scan.json").write_text(
        json.dumps(scan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print("== V2 候选扫描（R1 口径：mf 主指标，端点帧不动） ==")
    print("baseline mf_peak: wave 22.09 / cross 0.0 / jab 80.22")
    for r in results:
        print(f"\n[{r['name']}] passed={r['passed']} "
              f"changed={r['changed_frame_total']} 帧")
        print("  mf_peak  wave %.3f / cross %.3f / jab %.3f  "
              "wave>=55=%s cross>=25=%s jab不动=%s"
              % (r["tier_mf_peak_px"]["wave"], r["tier_mf_peak_px"]["cross"],
                 r["tier_mf_peak_px"]["jab"],
                 r["checks"]["wave_arm_drive_strong"],
                 r["checks"]["cross_arm_drive_strong"],
                 r["checks"]["jab_byte_identical_for_reach_probe"]))
        print("  mf peak phase: %s" % r["attack_mf_peak_phase"])
        print("  cross recoil=%.3f arc=%.3f / wave arc=%.3f"
              % (r["cross_windup_recoil_px"], r["cross_arc_deviation_px"],
                 r["wave_arc_deviation_px"]))
        print("  holds=%d drift=%.4f(%s) 2D=%.3f(%s) 3D=%.4f°(%s)"
              % (r["exact_hold_pairs"], r["endpoint_drift_px"],
                 r["endpoint_drift_at"], r["max_2d_shift_px"],
                 r["max_2d_shift_at"], r["max_3d_delta_diff_deg"],
                 r["max_3d_delta_diff_at"]))
        print("  L8 min pair=%.3f (%s) failed=%s"
              % (r["l8_peak_pair_min"], r["l8_peak_pair_at"],
                 [k for k, v in r["checks"].items() if not v]))
    if pick is None:
        print("\nNO_CANDIDATE_PASSED")
        return 1
    print("\nRECOMMENDED", pick["name"])
    tracks_out = {
        "source": "P4 上线态 card_motion.json（三份表当前逐值同步）",
        "metric_revision": "R1+R2",
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
    print("POSE_CANDIDATES_V2_OK" if ok else "POSE_CANDIDATES_V2_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
