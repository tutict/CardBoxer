"""《牌拳》角色动作表现 P2 · 幅度瓶颈诊断（纯读盘 + 纯计算，不改任何文件）。

回答三个「别凭印象」的问题：
  Q1 腿：leg_cap_deg=3 到底砍掉了多少 2D 动作表里的腿部信号？
         候选 cap 3/6/9/12/无上限 各自的送达率与残余削角帧数。
  Q2 双臂：15 条轨道里，有没有「前后手同时大幅动」的？还是源数据
         本身就一招只动一只手？wave_arm_weight 的双手信号实际触发几帧？
  Q3 成本：历史 C 路线 gain_sweep 的 mapping 口径是否与当前游戏一致，
         它的可用增益区间能不能直接拿来做 P2 上限（适用边界写清楚）。

判据一律从 card_motion.json 的 15 轨 284 帧重算，不引用上游 ok 字段。

用法：python diag_p2.py
产出：data/p2_diagnosis.json
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DIAG = BAKE / "motion-diagnostics"
HIST = BAKE / "route-c-real-3d-fix"
PUPPET = BAKE / "3d-attack-gifs" / "puppet_mapping.json"
OUT = HERE / "data" / "p2_diagnosis.json"

import sys  # noqa: E402
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
ARM_BONES = ("upperarm_f", "forearm_f", "upperarm_b", "forearm_b")
CANDIDATE_CAPS = (3.0, 6.0, 9.0, 12.0, 1e9)
CANDIDATE_ARM_GAINS = (1.0, 1.25, 1.5, 2.0)
DUAL_ARM_THRESHOLD_DEG = 8.0


def pct(values, q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    i = min(len(xs) - 1, int(math.ceil(q * len(xs))) - 1)
    return round(xs[i], 4)


def summarize(values) -> dict:
    xs = [float(v) for v in values]
    if not xs:
        return {"n": 0, "mean": 0.0, "p95": 0.0, "max": 0.0}
    return {"n": len(xs), "mean": round(sum(xs) / len(xs), 4),
            "p95": pct(xs, 0.95), "max": round(max(xs), 4)}


def arm_signals(frame_j, stance_j, mapping) -> tuple[float, float, float]:
    """复算 rig_driver.gd 的 af / ab / tw（诊断用，不写回源码）。"""
    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])
    mf = dist(frame_j["f_hand"], stance_j["f_hand"])
    mb = dist(frame_j["b_hand"], stance_j["b_hand"])
    tf = min(1.0, mf / float(mapping["reach_norm_px"]))
    tb = min(1.0, mb / float(mapping["reach_norm_px"]))
    tw = (min(1.0, min(mf, mb) / float(mapping["wave_min_norm_px"]))
          * float(mapping["wave_arm_weight"]))
    return max(tf, tw), max(tb, tw), tw


def main() -> int:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    puppet = json.loads(PUPPET.read_text(encoding="utf-8"))
    sweep = json.loads((HIST / "gain_sweep.json").read_text(
        encoding="utf-8"))
    driver_src = (GAME / "scripts" / "rig_driver.gd").read_text(
        encoding="utf-8")

    tracks = {k: v["track"] for k, v in cm["cards"].items()}
    tracks.update({k: v["track"] for k, v in cm["motions"].items()})
    keys = list(mi["joint_names"])
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    stance_points = make_points(stance_j)
    chain, mapping = mi["chain"], mi["mapping"]
    leg_cap = float(mapping["leg_cap_deg"])

    raw_leg_all, delivered_leg_all = [], []
    raw_torso_all = []
    leg_frames_clipped = 0
    torso_cap_hits = 0
    total_frames = 0
    af_all, ab_all, tw_all = [], [], []
    dual_signal_frames = 0
    per_track = {}

    for name, track in tracks.items():
        peaks = {n: 0.0 for n in LEG_BONES + ARM_BONES}
        raw_peak_leg = 0.0
        clipped = 0
        dual = 0
        af_peak = ab_peak = 0.0
        for frame in track:
            fj = {k: tuple(frame[k]) for k in keys}
            d, raw = retarget_delta(fj, stance_j, chain, mapping,
                                    stance_points)
            total_frames += 1
            af, ab, tw = arm_signals(fj, stance_j, mapping)
            af_all.append(af)
            ab_all.append(ab)
            tw_all.append(tw)
            af_peak = max(af_peak, af)
            ab_peak = max(ab_peak, ab)
            if af > 0.2 and ab > 0.2:
                dual_signal_frames += 1
                dual += 1
            for n in LEG_BONES:
                r = abs(float(raw[n]))
                v = abs(float(d[n]))
                raw_leg_all.append(r)
                delivered_leg_all.append(v)
                raw_peak_leg = max(raw_peak_leg, r)
                peaks[n] = max(peaks[n], v)
                if r > leg_cap + 1e-6:
                    clipped += 1
            for n in ARM_BONES:
                peaks[n] = max(peaks[n], abs(float(d[n])))
            raw_torso_all.append(abs(float(raw["spine"])))
            if abs(float(d["spine"])) >= float(mapping["torso_cap_deg"]) - 1e-6:
                torso_cap_hits += 1
        if clipped:
            leg_frames_clipped += 1
        arm_f = max(peaks["upperarm_f"], peaks["forearm_f"])
        arm_b = max(peaks["upperarm_b"], peaks["forearm_b"])
        per_track[name] = {
            "frames": len(track),
            "raw_leg_peak_deg": round(raw_peak_leg, 3),
            "leg_clipped_bone_frames": clipped,
            "delivered_leg_peak_deg": round(max(peaks[n] for n in LEG_BONES), 3),
            "arm_f_peak_deg": round(arm_f, 3),
            "arm_b_peak_deg": round(arm_b, 3),
            "both_arms_ge_8deg": (arm_f >= DUAL_ARM_THRESHOLD_DEG
                                  and arm_b >= DUAL_ARM_THRESHOLD_DEG),
            "one_arm_frozen": min(arm_f, arm_b) < 2.0,
            "af_peak": round(af_peak, 4), "ab_peak": round(ab_peak, 4),
            "dual_signal_frames": dual,
        }

    # Q1：候选 leg_cap 的送达率（不改源数据，只换 clamp 常数重算）
    cap_rows = {}
    for cap in CANDIDATE_CAPS:
        m2 = copy.deepcopy(mapping)
        m2["leg_cap_deg"] = cap
        vals, still = [], 0
        for name, track in tracks.items():
            for frame in track:
                fj = {k: tuple(frame[k]) for k in keys}
                _d, raw = retarget_delta(fj, stance_j, chain, m2,
                                         stance_points)
                for n in LEG_BONES:
                    r = abs(float(raw[n]))
                    v = min(r, cap)
                    vals.append(v)
                    if r > cap + 1e-6:
                        still += 1
        cap_rows[str(cap)] = {
            "delivered_abs": summarize(vals),
            "signal_delivery_ratio": round(
                sum(vals) / max(1e-9, sum(raw_leg_all)), 4),
            "bone_frames_still_clipped": still,
        }

    # Q2/Q3：候选 arm_gain 的峰值幅度（对应历史 sweep 的 gain 档）
    gain_rows = {}
    for g in CANDIDATE_ARM_GAINS:
        m2 = copy.deepcopy(mapping)
        m2["arm_gain_deg"] = {
            k: v * g for k, v in mapping["arm_gain_deg"].items()}
        vals = []
        for name, track in tracks.items():
            for frame in track:
                fj = {k: tuple(frame[k]) for k in keys}
                d, _raw = retarget_delta(fj, stance_j, chain, m2,
                                         stance_points)
                vals.append(max(abs(float(d[n])) for n in ARM_BONES))
        gain_rows[str(g)] = {
            "arm_peak_deg": round(max(vals), 3),
            "arm_abs_deg": summarize(vals),
            "arm_gain_deg": m2["arm_gain_deg"],
        }

    # 历史口径核对：只比数值，不信历史报告自己的「可复用」措辞
    puppet_vals = {k: v for k, v in puppet.items()
                   if not k.startswith("_")}
    mapping_equal = all(puppet_vals.get(k) == v for k, v in mapping.items())
    sweep_rows = sweep["rows"]
    hist_worst = max(r["p999_edge_tear_m"] for r in sweep_rows)
    hist_arm15 = [r for r in sweep_rows
                  if r["mode"] == "arm_only" and r["gain"] == 1.5]

    diagnosis = {
        "inputs": {
            "tracks": len(tracks), "total_frames": total_frames,
            "mapping_leg_cap_deg": leg_cap,
            "mapping_arm_gain_deg": mapping["arm_gain_deg"],
            "historical_sweep": str(HIST / "gain_sweep.json"),
        },
        "q1_leg": {
            "raw_abs_deg": summarize(raw_leg_all),
            "delivered_abs_deg": summarize(delivered_leg_all),
            "signal_delivery_ratio_at_current_cap": round(
                sum(delivered_leg_all) / max(1e-9, sum(raw_leg_all)), 4),
            "frames_with_clipped_leg_bone": leg_frames_clipped,
            "candidate_caps": cap_rows,
        },
        "q2_arms": {
            "dual_arm_threshold_deg": DUAL_ARM_THRESHOLD_DEG,
            "tracks_with_both_arms": sorted(
                k for k, v in per_track.items() if v["both_arms_ge_8deg"]),
            "tracks_with_one_arm_frozen": sorted(
                k for k, v in per_track.items() if v["one_arm_frozen"]),
            "dual_signal_frames": dual_signal_frames,
            "af": summarize(af_all), "ab": summarize(ab_all),
            "tw": summarize(tw_all),
            "candidate_arm_gains": gain_rows,
        },
        "q3_torso": {
            "raw_spine_abs_deg": summarize(raw_torso_all),
            "cap_hit_frames": torso_cap_hits,
            "cap_deg": float(mapping["torso_cap_deg"]),
        },
        "historical_cost_anchor": {
            "puppet_mapping_values_equal_current": mapping_equal,
            "baseline_mapping_sha256": sweep["baseline_mapping_sha256"],
            "rigid_baseline_p999_m": sweep["verdict"]["rigid_baseline_p999_m"],
            "worst_sweep_p999_m": hist_worst,
            "worst_over_rigid": sweep["verdict"]["worst_over_rigid"],
            "arm15_p999_m": [r["p999_edge_tear_m"] for r in hist_arm15],
            "usable_gain_range": sweep["verdict"]["usable_gain_range"],
            "root_cause": sweep["verdict"]["root_cause"],
            "applicability_boundary": (
                "历史 sweep 在对手怪 V1 高模、3 卡各 1 帧、Blender CPU "
                "evaluated mesh 上测得；当前游戏是 player-rigged.glb / "
                "foe-rigged.glb 的 GPU skin、15 卡 284 帧。公式同口径但"
                "网格与帧集不同，只能当作方向性锚，不能直接当放行上限。"),
        },
        "per_track": per_track,
        "source_formula_present": {
            "leg_is_hard_clamp": 'clampf(float(raw["thigh_f"]), -leg_cap, leg_cap)'
            in driver_src,
            "arm_is_gain_times_signal": '"upperarm_f": -float(g["f_upper"]) * af'
            in driver_src,
        },
    }
    checks = {
        "fifteen_tracks": len(tracks) == 15,
        "284_frames": total_frames == 284,
        "leg_is_hard_clamp": diagnosis["source_formula_present"]["leg_is_hard_clamp"],
        "arm_is_gain_times_signal":
            diagnosis["source_formula_present"]["arm_is_gain_times_signal"],
        "raw_leg_signal_exceeds_cap": max(raw_leg_all) > leg_cap,
        "cap_raises_delivery": (
            cap_rows["12.0"]["signal_delivery_ratio"]
            > cap_rows["3.0"]["signal_delivery_ratio"]),
        "puppet_mapping_same_values": mapping_equal,
        "historical_sweep_has_arm15": len(hist_arm15) == 3,
        "candidate_gains_monotonic": all(
            gain_rows[str(CANDIDATE_ARM_GAINS[i])]["arm_peak_deg"]
            < gain_rows[str(CANDIDATE_ARM_GAINS[i + 1])]["arm_peak_deg"]
            for i in range(len(CANDIDATE_ARM_GAINS) - 1)),
    }
    diagnosis["checks"] = checks
    diagnosis["ok"] = all(checks.values())
    OUT.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print("TRACKS", len(tracks), "FRAMES", total_frames)
    print("LEG raw", diagnosis["q1_leg"]["raw_abs_deg"],
          "delivered", diagnosis["q1_leg"]["delivered_abs_deg"],
          "delivery", diagnosis["q1_leg"]["signal_delivery_ratio_at_current_cap"])
    for cap, row in cap_rows.items():
        print("CAP", cap, "delivery", row["signal_delivery_ratio"],
              "peak", row["delivered_abs"]["max"],
              "still_clipped", row["bone_frames_still_clipped"])
    print("DUAL_ARM_TRACKS", diagnosis["q2_arms"]["tracks_with_both_arms"])
    print("ONE_ARM_FROZEN", diagnosis["q2_arms"]["tracks_with_one_arm_frozen"])
    print("DUAL_SIGNAL_FRAMES", dual_signal_frames)
    for g, row in gain_rows.items():
        print("ARM_GAIN", g, "peak_deg", row["arm_peak_deg"])
    print("TORSO cap hits", torso_cap_hits)
    print("HIST mapping_equal", mapping_equal, "worst_p999", hist_worst,
          "arm15", [r["p999_edge_tear_m"] for r in hist_arm15])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("DIAG_P2_OK" if diagnosis["ok"] else "DIAG_P2_FAILED")
    return 0 if diagnosis["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
