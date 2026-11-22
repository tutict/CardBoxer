"""P4 · 落地决策 + 生成 micro2 改动清单 / 全量 284 帧 Blender 姿态计划。

订正上一轮候选扫描的自动推荐：evaluate_candidates.py 按「可辨平台最低」
选出 hybrid_lerp_micro03，但那个档把整帧定格段改成 LERP 匀速过渡，
2D 关节最大位移 33.0606 px —— 这是重设动画语义，不是修数值平台。
255 对原生平台里 224 对本来就是 11 关节完全相同的设计定格帧。

本轮落地选 micro_2：段内严格递增的微扰，幅度上限 2 px。
首版用四分之一正弦且没保护端点，实测把 pose_probe 的「表内起收招
最大漂移」从 1.100 px 推到 1.569 px（红线 1.5 px）——扰动堆到了
wave 末帧，而末帧是收招归位帧。本版保护每条 track 的首帧/末帧不扰动，
段内改用 w = A*(k+1)/(m+2)（恒 > 0 且严格递增），平台仍归零，
2D 关节位移不足 2 px，三份表 11 关节仍逐值相同。

同时证明三份表的 round-trip 序列化恒等，apply_native.py 才能用
「load -> 改数值 -> 用同格式 dump」做字节级最小改动，而不是脆弱的
文本 needle 替换（定格帧在文本里会重复出现，needle 不唯一）。

用法：python make_landing.py
产出：data/landing_decision.json、data/landing_tracks.json、
      data/micro2_plan.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DIAG = BAKE / "motion-diagnostics"
D = HERE / "data"
sys.path.insert(0, str(DIAG))
sys.path.insert(0, str(HERE))
from diag_motion import retarget_delta  # noqa: E402
from evaluate_candidates import (  # noqa: E402
    CAP, DIRECTIONS, EXACT_EPS, LEG_BONES, Ctx, frame_joints,
    leg_value, measure, segments_of,
)

AMPLITUDE = 2.0
CASE = f"micro_{AMPLITUDE:g}"
LEG_JOINTS = ("f_knee", "f_foot", "b_knee", "b_foot")

MI = GAME / "data" / "motion_input.json"
MIF = GAME / "data" / "motion_input_foe.json"
CM = GAME / "data" / "card_motion.json"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dumps_mi(obj: dict) -> bytes:
    return (json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode("utf-8")


def dumps_cm(obj: dict) -> bytes:
    return json.dumps(obj, indent=1, ensure_ascii=False).replace(
        "\n", "\r\n").encode("utf-8")


def tracks_of(d: dict) -> dict:
    out = {k: v["track"] for k, v in d["cards"].items()}
    out.update({k: v["track"] for k, v in d.get("motions", {}).items()})
    return out


def build_micro_protected(joints: list[dict], flags: list[bool],
                          amplitude: float) -> list[dict]:
    """段内严格递增微扰，且保护 track 首帧 / 末帧（起手/收招归位帧）。

    四分之一正弦在 k=0 给 w=0、k=m 给 w≈A，正好把位移堆到段末；
    若段末就是 track 末帧，会撞 pose_probe 的 1.5 px 归位红线。
    线性 w = A*(k+1)/(m+2) 恒 > 0 且严格递增：段首也有非零扰动，
    所以「保护段末」不会让最后一对平台残留；相邻帧永远拿到不同 w。
    """
    out = [dict(j) for j in joints]
    protected = {0, len(joints) - 1}
    for s, m in segments_of(flags):
        for k in range(m + 1):
            j = s + k
            if j in protected:
                continue
            w = amplitude * (k + 1) / (m + 2)
            for name, (dx, dy) in DIRECTIONS.items():
                ox, oy = joints[j][name]
                out[j][name] = (round(ox + dx * w, 6),
                                round(oy + dy * w, 6))
    return out


def main() -> int:
    mi, mif, cm = load(MI), load(MIF), load(CM)
    scan = load(D / "candidate_scan.json")
    tear = load(D / "native_tear.json")
    plan_ref = load(D / "native_plan.json")

    # 1) round-trip 恒等证明：apply 才能安全地整体重序列化
    roundtrip = {
        "motion_input.json": MI.read_bytes() == dumps_mi(mi),
        "motion_input_foe.json": MIF.read_bytes() == dumps_mi(mif),
        "card_motion.json": CM.read_bytes() == dumps_cm(cm),
    }

    # 2) micro2 改动清单（沿用候选扫描的 flags，扰动形状改为端点保护版）
    ctx = Ctx(mi)
    keys = ctx.keys
    tracks = tracks_of(cm)
    base, flags, edits, changed, per = {}, {}, {}, {}, {}
    endpoint_ok = {}
    for card, track in tracks.items():
        base[card] = [frame_joints(f, keys) for f in track]
        raws = [ctx.raw(j) for j in base[card]]
        flags[card] = [
            any(abs(raws[i + 1][b] - raws[i][b]) < EXACT_EPS
                for b in LEG_BONES)
            for i in range(len(track) - 1)]
        mod = build_micro_protected(base[card], flags[card],
                                    AMPLITUDE)
        per[card] = measure(ctx, base[card], mod)
        endpoint_ok[card] = (mod[0] == base[card][0]
                             and mod[-1] == base[card][-1])
        rows = {}
        for i, (a, b) in enumerate(zip(base[card], mod)):
            diff = {j: [round(float(b[j][0]), 6),
                        round(float(b[j][1]), 6)]
                    for j in LEG_JOINTS if a[j] != b[j]}
            if diff:
                rows[str(i)] = diff
        edits[card] = rows
        changed[card] = sorted(int(i) for i in rows)

    agg = {
        "exact_flat_pairs": sum(p["exact_flat_pairs"] for p in per.values()),
        "perceptual_flat_pairs": sum(
            p["perceptual_flat_pairs"] for p in per.values()),
        "changed_frames": sum(p["changed_frames"] for p in per.values()),
        "max_joint_delta_px": max(
            p["max_joint_delta_px"] for p in per.values()),
        "max_adjacent_jump_px": max(
            p["max_adjacent_jump_px"] for p in per.values()),
        "baseline_max_adjacent_jump_px": max(
            p["baseline_max_adjacent_jump_px"] for p in per.values()),
    }
    scan_row = scan["rows"][CASE]

    # 3) 单档 micro2 × 全量 284 帧 Blender 姿态计划
    cfg = dict(mi["mapping"])
    cfg["leg_cap_deg"] = 1e9
    px_to_m = float(mi["px_to_m"])
    poses = []
    for card, track in tracks.items():
        mod = build_micro_protected(base[card], flags[card],
                                    AMPLITUDE)
        for i in range(len(track)):
            fj = {k: tuple(v) for k, v in mod[i].items()}
            d, raw = retarget_delta(fj, ctx.stance, ctx.chain, cfg,
                                    ctx.points)
            dd = {n: float(d[n]) for n in d}
            for b in LEG_BONES:
                dd[b] = leg_value(float(raw[b]))
            dx = (fj["hip"][0] - ctx.stance["hip"][0]) * px_to_m
            dz = -(fj["hip"][1] - ctx.stance["hip"][1]) * px_to_m
            poses.append({"case": CASE, "card": card, "frame": i,
                          "why": "all_frames", "delta_deg": dd,
                          "root_m": [dx, dz]})
    plan = {
        "glb": plan_ref["glb"], "px_to_m": px_to_m,
        "chain": plan_ref["chain"],
        "apose_points": mi["apose_points"], "bones": mi["bones"],
        "cases": [{"id": CASE, "leg_cap_deg": CAP, "leg_mode": "atan",
                   "purpose": "landing_candidate",
                   "arm_gain_multiplier": 1.0,
                   "arm_gain_deg": dict(mi["mapping"]["arm_gain_deg"])}],
        "poses": poses, "frame_count": len(poses),
        "frames": [{"card": p["card"], "frame": p["frame"],
                    "why": "all_frames"} for p in poses],
        "legend": {
            "delta_deg": "rig_driver.gd::retarget_delta 同公式，单位度",
            CASE: "端点保护 + 段内线性递增微扰，上限 2 px，只改四个腿关节",
        },
    }
    (D / "micro2_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    landing_tracks = {
        "case": CASE, "amplitude_px": AMPLITUDE,
        "leg_joints": list(LEG_JOINTS),
        "flags_definition": "相邻帧任一腿骨 raw delta 差 < 1e-6",
        "build_rule": (
            "w = A*(k+1)/(m+2)，段内恒 > 0 且严格递增；"
            "每条 track 的首帧与末帧（起手/收招归位帧）不扰动"),
        "protected_endpoints_identical": endpoint_ok,
        "changed_frames": changed,
        "changed_frame_total": sum(len(v) for v in changed.values()),
        "edits": edits,
        "measure_recomputed": agg,
        "measure_from_candidate_scan": {
            k: scan_row[k] for k in agg},
        "tracks": len(tracks), "frames": sum(len(t) for t in tracks.values()),
    }
    (D / "landing_tracks.json").write_text(
        json.dumps(landing_tracks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    baseline = tear["per_case"]["baseline"]
    decision = {
        "decision": "落地 micro2，三份表同步；否决候选扫描推荐的 hybrid",
        "why_hybrid_rejected": (
            "hybrid 的 2D 关节最大位移 33.0606 px 来自 build_lerp 把整帧"
            "定格段改成匀速过渡，等于重设动画语义；诊断显示 255 对原生"
            "平台中 224 对是 11 关节完全相同的整帧定格 hold 帧，属设计"
            "意图而非缺陷。用户要求的是攻数值平台，不是重设动作。"),
        "why_micro2": (
            "段内 w = A*(k+1)/(m+2) 线性递增，恒 > 0、相邻帧必不同、"
            "不累积漂移；每条 track 的首帧与末帧是起手/收招归位帧，"
            "刻意不扰动，避免撞 pose_probe 的 1.5 px 归位红线（首版"
            "四分之一正弦把 wave 末帧推到 1.569 px 已实测判红）。"
            "幅度上限 2 px 在 2D 侧不足 2 像素不可见；三份表 11 关节"
            "同步修改，跨表对账守卫保持成立。"),
        "amplitude_px": AMPLITUDE,
        "build_rule": landing_tracks["build_rule"],
        "cost_table": {
            "baseline": {
                "exact_flat_pairs": baseline["exact_flat_pairs"],
                "perceptual_flat_pairs": baseline["perceptual_flat_pairs"],
                "max_joint_delta_px": baseline["max_joint_delta_px"],
                "worst_p999_m": baseline["worst_p999_m"]},
            CASE: {
                "exact_flat_pairs": agg["exact_flat_pairs"],
                "perceptual_flat_pairs": agg["perceptual_flat_pairs"],
                "max_joint_delta_px": agg["max_joint_delta_px"],
                "worst_p999_m": None},
            "micro05": {
                k: tear["per_case"]["micro05"][k]
                for k in ("exact_flat_pairs", "perceptual_flat_pairs",
                          "max_joint_delta_px", "worst_p999_m")},
            "hybrid": {
                k: tear["per_case"]["hybrid"][k]
                for k in ("exact_flat_pairs", "perceptual_flat_pairs",
                          "max_joint_delta_px", "worst_p999_m")},
        },
        "anchor_p999_m": tear["anchor_p999_m"],
        "roundtrip_identity": roundtrip,
        "scan_recommended_case": scan["recommended_case"],
        "checks": {
            "all_three_roundtrip_identical": all(roundtrip.values()),
            "all_track_endpoints_untouched": all(endpoint_ok.values()),
            "no_endpoint_frame_in_edits": all(
                0 not in changed[c]
                and len(tracks[c]) - 1 not in changed[c]
                for c in tracks),
            "exact_flat_reaches_zero": agg["exact_flat_pairs"] == 0,
            "perceptual_below_baseline": (
                agg["perceptual_flat_pairs"]
                < baseline["perceptual_flat_pairs"]),
            "max_displacement_under_2px": agg["max_joint_delta_px"] < 2.0,
            "hybrid_displacement_much_larger": (
                tear["per_case"]["hybrid"]["max_joint_delta_px"]
                > 10 * agg["max_joint_delta_px"]),
            "no_worsened_adjacent_jump": (
                agg["max_adjacent_jump_px"]
                <= agg["baseline_max_adjacent_jump_px"] + 1e-9),
            "plan_284_poses": len(poses) == 284,
            "plan_tracks_15": len(tracks) == 15,
            "no_nan_in_plan_deltas": all(
                v == v for p in poses for v in p["delta_deg"].values()),
            "segments_nonempty": sum(
                len(segments_of(f)) for f in flags.values()) > 0,
        },
    }
    decision["failed"] = [k for k, v in decision["checks"].items()
                          if not v]
    decision["ok"] = all(decision["checks"].values())
    (D / "landing_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print("CASE", CASE, "AMPLITUDE", AMPLITUDE)
    print("ROUNDTRIP", roundtrip)
    print("RECOMPUTED", agg)
    print("SCAN", {k: scan_row[k] for k in agg})
    print("POSES", len(poses), "CHANGED_FRAMES",
          landing_tracks["changed_frame_total"])
    for k, v in decision["checks"].items():
        print("CHECK", k, v)
    print("LANDING_OK" if decision["ok"] else "LANDING_FAILED")
    return 0 if decision["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
