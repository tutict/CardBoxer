"""P1 幅度门禁：独立复算 12 卡 + 3 受击轨道的 13 骨 delta。

不放大任何增益；用 motion_input.json 里既有的 mapping 理论上限做硬门禁，
并标出相对「既有 3 卡峰值」明显变大的轨道（需要渲图看撕裂）。

用法：python scan_amplitude.py
产出：data/amplitude_scan.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "牌拳-CardBoxer"
sys.path.insert(0, str(HERE.parent / "动作优化诊断"))
from diag_motion import make_points, retarget_delta  # noqa: E402

OUT = HERE / "data" / "amplitude_scan.json"
EXISTING = ("jab", "cross", "wave")
COORD_X_MAX = 400.0
COORD_Y_MIN, COORD_Y_MAX = -300.0, 120.0


def joints_of(frame: dict, keys) -> dict:
    return {k: tuple(frame[k]) for k in keys}


def coord_ok(frame: dict, keys) -> bool:
    for k in keys:
        if k not in frame:
            return False
        v = frame[k]
        if not (isinstance(v, (list, tuple)) and len(v) == 2):
            return False
        if not (abs(float(v[0])) <= COORD_X_MAX
                and COORD_Y_MIN <= float(v[1]) <= COORD_Y_MAX):
            return False
    return True


def main() -> int:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    keys = list(mi["joint_names"])
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    stance_points = make_points(stance_j)
    chain, mapping = mi["chain"], mi["mapping"]

    g = mapping["arm_gain_deg"]
    limits = {
        "hips": 0.0, "spine": float(mapping["torso_cap_deg"]),
        "chest": 0.0, "neck": 0.0,
        "head": float(mapping["torso_cap_deg"]) *
                float(mapping["head_compensation"]),
        "upperarm_f": float(g["f_upper"]), "forearm_f": float(g["f_fore"]),
        "upperarm_b": float(g["b_upper"]), "forearm_b": float(g["b_fore"]),
        "thigh_f": float(mapping["leg_cap_deg"]),
        "shin_f": float(mapping["leg_cap_deg"]),
        "thigh_b": float(mapping["leg_cap_deg"]),
        "shin_b": float(mapping["leg_cap_deg"]),
    }

    tracks = {}
    for k, v in cm["cards"].items():
        tracks[k] = v["track"]
    for k, v in cm["motions"].items():
        tracks[k] = v["track"]

    rows = {}
    for name, track in tracks.items():
        peaks = {n: 0.0 for n in limits}
        all_coord_ok = True
        all_keys_ok = True
        for frame in track:
            if not all(k in frame for k in keys):
                all_keys_ok = False
                continue
            if not coord_ok(frame, keys):
                all_coord_ok = False
            fj = joints_of(frame, keys)
            d, _raw = retarget_delta(fj, stance_j, chain, mapping,
                                     stance_points)
            for n, v in d.items():
                peaks[n] = max(peaks[n], abs(v))
        first = joints_of(track[0], keys) if track and all(
            k in track[0] for k in keys) else {}
        first_is_stance = bool(first) and all(
            first[k] == stance_j[k] for k in keys)
        over = {n: round(peaks[n] - limits[n], 4)
                for n in limits if peaks[n] > limits[n] + 1e-6}
        rows[name] = {
            "frames": len(track),
            "peak_abs_deg": {n: round(v, 3) for n, v in peaks.items()},
            "within_limits": not over, "over_by_deg": over,
            "coord_ok": all_coord_ok, "joint_keys_ok": all_keys_ok,
            "first_frame_is_stance": first_is_stance,
            "kind": "existing" if name in EXISTING else (
                "react" if name in cm["motions"] else "new"),
        }

    base_peaks = {}
    for n in limits:
        vals = [rows[k]["peak_abs_deg"][n] for k in EXISTING
                if k in rows]
        base_peaks[n] = max(vals) if vals else 0.0
    for name, row in rows.items():
        ratios = [row["peak_abs_deg"][n] / base_peaks[n]
                  for n in limits if base_peaks[n] > 1e-6]
        row["ratio_vs_existing_peak"] = round(max(ratios), 3) if ratios else 0.0
        row["needs_visual_check"] = row["ratio_vs_existing_peak"] > 1.2

    checks = {
        "track_count_15": len(tracks) == 15,
        "existing_three_present": all(k in rows for k in EXISTING),
        "new_tracks_twelve": sum(r["kind"] != "existing"
                                 for r in rows.values()) == 12,
        "all_within_mapping_limits": all(r["within_limits"]
                                         for r in rows.values()),
        "all_coords_sane": all(r["coord_ok"] for r in rows.values()),
        "all_joint_keys_present": all(r["joint_keys_ok"]
                                      for r in rows.values()),
        "all_tracks_nonempty": all(r["frames"] > 0 for r in rows.values()),
    }
    report = {
        "limits_deg": limits,
        "existing_peak_deg": {n: round(v, 3) for n, v in base_peaks.items()},
        "tracks": rows,
        "gate_conclusion": (
            "全部轨道落在既有 mapping 理论上限内，不需要放大增益；"
            "ratio>1.2 的轨道只标记需渲图复核，不作为放行条件。"),
        "needs_visual_check": sorted(
            k for k, r in rows.items() if r["needs_visual_check"]),
        "checks": checks, "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("LIMITS", json.dumps(report["existing_peak_deg"]))
    for k, r in rows.items():
        print("TRACK", k, r["kind"], "frames", r["frames"],
              "peak", max(r["peak_abs_deg"].values()),
              "ratio", r["ratio_vs_existing_peak"],
              "within", r["within_limits"], "coord", r["coord_ok"])
    print("NEEDS_VISUAL_CHECK", report["needs_visual_check"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("AMPLITUDE_GATE_OK" if report["ok"]
          else "AMPLITUDE_GATE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
