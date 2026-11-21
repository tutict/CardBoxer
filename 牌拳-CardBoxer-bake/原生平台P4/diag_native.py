"""P4 · 原生平台诊断（纯读盘 + 纯计算，不改任何文件）。

要回答的问题（先诊断再动手）：
  Q1 P3 剩下的 255 对「原生平台」，是**整帧 11 关节完全相同**，
     还是只有腿关节钉住、上身仍在动？后者可能是动作设计意图。
  Q2 它们落在哪些轨道 / 哪些腿骨 / 哪些帧段，是否在 held_frames 定格区？
  Q3 数据层其实有两份：card_motion.json（2D 侧真相）与
     motion_input*.json 自带的 cards.track（3D 运行时真相）。
     两份当前是否逐值相同？改哪份影响面多大？
  Q4 要让平台消失，最小扰动需要多少像素 / 多少帧？
     给 1px 关节位移对腿骨 raw 角的数值微分，避免凭感觉定 epsilon。

用法：python diag_native.py
产出：data/native_diagnosis.json
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
DIAG = BAKE / "动作优化诊断"
OUT = HERE / "data" / "native_diagnosis.json"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
EXACT_EPS = 1e-6
PERCEPTUAL_EPS = 0.1


def frame_joints(frame: dict, keys: list[str]) -> dict:
    return {k: tuple(float(x) for x in frame[k]) for k in keys}


def raw_of(joints: dict, stance_j: dict, chain, mapping,
           stance_points) -> dict:
    _d, raw = retarget_delta(
        {k: tuple(v) for k, v in joints.items()},
        stance_j, chain, mapping, stance_points)
    return {b: float(raw[b]) for b in LEG_BONES}


def frame_delta_px(a: dict, b: dict) -> tuple[list[str], float]:
    """两帧 11 关节里哪些不同、最大坐标差（px）。"""
    changed, worst = [], 0.0
    for k in a:
        d = math.dist(a[k], b[k])
        if d > 1e-9:
            changed.append(k)
            worst = max(worst, d)
    return sorted(changed), round(worst, 4)


def main() -> int:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    mif = json.loads((GAME / "data" / "motion_input_foe.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    keys = list(mi["joint_names"])
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    stance_points = make_points(stance_j)
    chain = mi["chain"]
    mapping = dict(mi["mapping"])
    mapping["leg_cap_deg"] = 1e9  # 拿未经映射的原始腿角

    cm_tracks = {k: v["track"] for k, v in cm["cards"].items()}
    cm_tracks.update({k: v["track"] for k, v in cm["motions"].items()})
    mi_tracks = {k: v["track"] for k, v in mi["cards"].items()}
    foe_tracks = {k: v["track"] for k, v in mif["cards"].items()}

    # ── Q3 两份数据层是否逐值相同 ────────────────────────────
    same_names = sorted(cm_tracks) == sorted(mi_tracks)
    cross_diff: dict[str, list[int]] = {}
    for card in sorted(cm_tracks):
        a, b = cm_tracks[card], mi_tracks.get(card, [])
        bad = []
        if len(a) != len(b):
            cross_diff[card] = [-1]
            continue
        for i, (fa, fb) in enumerate(zip(a, b)):
            for k in keys:
                if tuple(float(x) for x in fa[k]) != tuple(
                        float(x) for x in fb[k]):
                    bad.append(i)
                    break
        if bad:
            cross_diff[card] = bad
    player_foe_tracks_equal = all(
        mi_tracks[c] == foe_tracks.get(c) for c in mi_tracks)

    # ── Q1/Q2 逐帧拆 255 对 ──────────────────────────────────
    pairs = []
    for card, track in cm_tracks.items():
        raws = []
        for fr in track:
            raws.append(raw_of(frame_joints(fr, keys), stance_j, chain,
                               mapping, stance_points))
        for i in range(len(track) - 1):
            ja = frame_joints(track[i], keys)
            jb = frame_joints(track[i + 1], keys)
            changed, worst_px = frame_delta_px(ja, jb)
            held = int(cm["cards"].get(card, {}).get(
                "held_frames", cm["motions"].get(card, {}).get(
                    "held_frames", 0)) or 0)
            for bone in LEG_BONES:
                if abs(raws[i + 1][bone] - raws[i][bone]) < EXACT_EPS:
                    pairs.append({
                        "card": card, "frame": i, "bone": bone,
                        "raw_deg": round(raws[i][bone], 4),
                        "whole_frame_identical": not changed,
                        "changed_joints": changed,
                        "max_joint_delta_px": worst_px,
                        "phase_a": track[i].get("phase", ""),
                        "phase_b": track[i + 1].get("phase", ""),
                        "held_frames": held,
                        "in_hold_tail": i >= len(track) - held - 1,
                    })

    by_card = Counter(p["card"] for p in pairs)
    by_bone = Counter(p["bone"] for p in pairs)
    unique_frame_pairs = sorted({(p["card"], p["frame"]) for p in pairs})
    whole_identical = sum(p["whole_frame_identical"] for p in pairs)
    leg_only = sum(not p["whole_frame_identical"] for p in pairs)
    changed_joint_counter = Counter(
        j for p in pairs if not p["whole_frame_identical"]
        for j in p["changed_joints"])
    in_hold_tail = sum(p["in_hold_tail"] for p in pairs)

    # 唯一帧对里，整帧相同 vs 至少有一个关节在动
    uf_whole = sum(
        not frame_delta_px(
            frame_joints(cm_tracks[c][i], keys),
            frame_joints(cm_tracks[c][i + 1], keys))[0]
        for c, i in unique_frame_pairs)
    uf_moving = len(unique_frame_pairs) - uf_whole

    # 最长连续「整帧完全相同」段（按 card）
    longest_runs = []
    for card, track in cm_tracks.items():
        run, start, best, best_start = 0, 0, 0, 0
        for i in range(len(track) - 1):
            identical = not frame_delta_px(
                frame_joints(track[i], keys),
                frame_joints(track[i + 1], keys))[0]
            if identical:
                if run == 0:
                    start = i
                run += 1
                if run > best:
                    best, best_start = run, start
            else:
                run = 0
        if best:
            longest_runs.append({"card": card, "start": best_start,
                                 "end": best_start + best,
                                 "identical_pairs": best})
    longest_runs.sort(key=lambda r: -r["identical_pairs"])

    # ── Q4 数值微分：1px 关节位移能换来多少度 raw 变化 ─────────
    # 取一个非站架帧，分别给四个腿关节 +1px，看重算后的 raw 差。
    probe_card = "sweep"
    base = frame_joints(cm_tracks[probe_card][7], keys)
    base_raw = raw_of(base, stance_j, chain, mapping, stance_points)
    sensitivity = {}
    for joint in ("f_knee", "f_foot", "b_knee", "b_foot"):
        bump = dict(base)
        bump[joint] = (base[joint][0] + 1.0, base[joint][1])
        got = raw_of(bump, stance_j, chain, mapping, stance_points)
        sensitivity[joint] = {
            b: round(abs(got[b] - base_raw[b]), 4) for b in LEG_BONES}
    max_sens = max(v for s in sensitivity.values() for v in s.values())
    px_for_perceptual = round(PERCEPTUAL_EPS / max_sens, 4) \
        if max_sens > 0 else None

    # 精确到 1e-6° 只需极小扰动；真正要过「可辨」0.1° 才有视觉意义。
    # 统计：要让所有平台帧的腿骨变化 >= 0.1°，最少需要改多少帧。
    frames_to_edit = sorted({(p["card"], p["frame"] + 1)
                             for p in pairs})
    # 四条腿骨只由这四个腿关节决定；上半身关节不动就不会碰 2D 出拳语义。
    joints_to_edit = ["f_knee", "f_foot", "b_knee", "b_foot"]

    report = {
        "source": {
            "card_motion": str(GAME / "data" / "card_motion.json"),
            "motion_input": str(GAME / "data" / "motion_input.json"),
            "motion_input_foe": str(GAME / "data" / "motion_input_foe.json"),
        },
        "eps": {"exact_deg": EXACT_EPS, "perceptual_deg": PERCEPTUAL_EPS},
        "q1_structure": {
            "tracks": len(cm_tracks),
            "frames_total": sum(len(t) for t in cm_tracks.values()),
            "keys": keys,
            "same_track_names_in_two_tables": same_names,
            "cm_vs_mi_differing_frames": cross_diff,
            "cm_vs_mi_identical": not cross_diff,
            "player_foe_tracks_equal": player_foe_tracks_equal,
            "runtime_3d_reads": "motion_input*.json cards.track",
            "runtime_2d_reads": "card_motion.json cards/motions.track",
        },
        "q2_pairs": {
            "exact_flat_pairs": len(pairs),
            "unique_frame_pairs": len(unique_frame_pairs),
            "whole_frame_identical_pairs": whole_identical,
            "leg_only_identical_pairs": leg_only,
            "unique_frame_pairs_whole_identical": uf_whole,
            "unique_frame_pairs_with_motion": uf_moving,
            "in_hold_tail_pairs": in_hold_tail,
            "by_card": dict(sorted(by_card.items())),
            "by_bone": dict(sorted(by_bone.items())),
            "changed_joints_when_moving": dict(
                sorted(changed_joint_counter.items())),
            "longest_whole_frame_runs": longest_runs[:12],
        },
        "q4_sensitivity": {
            "probe": f"{probe_card}:7",
            "deg_per_1px": sensitivity,
            "max_deg_per_1px": max_sens,
            "px_needed_for_0_1deg": px_for_perceptual,
            "frames_to_edit_if_only_3d": len(frames_to_edit),
            "joint_names_to_edit": joints_to_edit,
            "example_frames": [list(x) for x in frames_to_edit[:12]],
        },
        "pairs": pairs,
    }
    checks = {
        "fifteen_tracks": len(cm_tracks) == 15,
        "frames_284": report["q1_structure"]["frames_total"] == 284,
        "native_pairs_matches_p3_floor": len(pairs) == 255,
        "native_plus_clamp_equals_p3_total": len(pairs) + 227 == 482,
        "split_sums": whole_identical + leg_only == len(pairs),
        "unique_frame_pairs_split": uf_whole + uf_moving
        == len(unique_frame_pairs),
        "p3_shipped_is_atan12": mi["mapping"]["leg_mode"] == "atan"
        and mi["mapping"]["leg_cap_deg"] == 12.0,
        "sensitivity_positive": max_sens > 0,
    }
    report["checks"] = checks
    report["failed"] = [k for k, v in checks.items() if not v]
    report["ok"] = all(checks.values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("TRACKS", len(cm_tracks), "FRAMES",
          report["q1_structure"]["frames_total"])
    print("CM_VS_MI_IDENTICAL", not cross_diff,
          "DIFF_FRAMES", sum(len(v) for v in cross_diff.values()))
    print("PLAYER_FOE_TRACKS_EQUAL", player_foe_tracks_equal)
    print("NATIVE_PAIRS", len(pairs), "UNIQUE_FRAME_PAIRS",
          len(unique_frame_pairs))
    print("WHOLE_IDENTICAL", whole_identical, "LEG_ONLY", leg_only)
    print("UNIQUE_WHOLE", uf_whole, "UNIQUE_MOVING", uf_moving)
    print("IN_HOLD_TAIL", in_hold_tail)
    print("BY_CARD", dict(sorted(by_card.items())))
    print("BY_BONE", dict(sorted(by_bone.items())))
    print("CHANGED_JOINTS", dict(sorted(changed_joint_counter.items())))
    print("LONGEST_RUNS", longest_runs[:6])
    print("DEG_PER_1PX", max_sens, "PX_FOR_0.1DEG", px_for_perceptual)
    print("FRAMES_TO_EDIT", len(frames_to_edit))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("NATIVE_DIAG_OK" if report["ok"] else "NATIVE_DIAG_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
