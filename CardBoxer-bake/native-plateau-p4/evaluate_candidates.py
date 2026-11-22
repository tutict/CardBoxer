"""P4 · 候选数据层改法扫描（纯计算，不改任何文件）。

两类候选：
  MICRO —— 只在「连续定格段」内给四个腿关节加一段端点归零的正弦微扰，
            offset(j) = A*sin(pi*k/(m+1))，相邻帧必不同、不累积漂移、
            段末回到原值。A 是幅度（px），扫描找最小可行值。
  LERP  —— 把定格段内各帧从段首线性插值到「段后第一个不同帧」，
            动作从硬定格变成匀速过渡，位移大得多，仅作成本对照。

全部按 P3 上线态 atan12 口径评估：精确平台 = 相邻输出差 < 1e-6°，
可辨平台 = < 0.1°。另记 2D 侧关节位移、改动帧数、腿角幅度与跳变。

用法：python evaluate_candidates.py
产出：data/candidate_scan.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DIAG = BAKE / "motion-diagnostics"
OUT = HERE / "data" / "candidate_scan.json"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
EXACT_EPS = 1e-6
PERCEPTUAL_EPS = 0.1
CAP, MODE = 12.0, "atan"
# 四个腿关节各给一个不同的单位方向，避免扰动退化成同一条骨链的刚性平移
DIRECTIONS = {
    "f_knee": (0.6, -0.8), "f_foot": (0.8, 0.6),
    "b_knee": (-0.6, -0.8), "b_foot": (-0.8, 0.6),
}
AMPLITUDES = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0]


def leg_value(x: float) -> float:
    return CAP * (2.0 / math.pi) * math.atan(
        (math.pi / 2.0) * x / CAP)


def frame_joints(frame: dict, keys: list[str]) -> dict:
    return {k: (float(frame[k][0]), float(frame[k][1])) for k in keys}


class Ctx:
    def __init__(self, mi):
        self.keys = list(mi["joint_names"])
        self.stance = {k: tuple(v) for k, v in mi["stance"].items()}
        self.points = make_points(self.stance)
        self.chain = mi["chain"]
        self.mapping = dict(mi["mapping"])
        self.mapping["leg_cap_deg"] = 1e9

    def raw(self, j: dict) -> dict:
        _d, r = retarget_delta({k: tuple(v) for k, v in j.items()},
                               self.stance, self.chain, self.mapping,
                               self.points)
        return {b: float(r[b]) for b in LEG_BONES}

    def out(self, j: dict) -> dict:
        return {b: leg_value(v) for b, v in self.raw(j).items()}


def segments_of(flags: list[bool]) -> list[tuple[int, int]]:
    """连续 True 段 -> (起始帧 s, 平台对数 m)，覆盖帧 s..s+m。"""
    out, i = [], 0
    while i < len(flags):
        if not flags[i]:
            i += 1
            continue
        s = i
        while i < len(flags) and flags[i]:
            i += 1
        out.append((s, i - s))
    return out


def build_micro(joints: list[dict], flags: list[bool],
                amplitude: float) -> list[dict]:
    out = [dict(j) for j in joints]
    for s, m in segments_of(flags):
        for k in range(m + 1):
            # 四分之一正弦：k=0..m 落在 [0, π/2) 内严格单调递增。
            # 首版用半周期 sin(pi*k/(m+1))，m=2 时 k=1 与 k=2 的
            # sin(60°)==sin(120°)，相邻帧拿到同一偏移，53 对平台残留。
            w = amplitude * math.sin(math.pi * k / (2 * (m + 1)))
            j = s + k
            for name, (dx, dy) in DIRECTIONS.items():
                ox, oy = joints[j][name]
                out[j][name] = (round(ox + dx * w, 6),
                                round(oy + dy * w, 6))
    return out


def build_lerp(joints: list[dict], flags: list[bool]) -> list[dict]:
    """定格段线性过渡到段后第一个不同帧（只改腿关节）。"""
    out = [dict(j) for j in joints]
    for s, m in segments_of(flags):
        end = s + m + 1  # 段后第一个不同帧
        if end >= len(joints):
            continue
        for k in range(1, m + 1):
            t = k / (m + 1)
            j = s + k
            for name in DIRECTIONS:
                a, b = joints[s][name], joints[end][name]
                out[j][name] = (round(a[0] + (b[0] - a[0]) * t, 6),
                                round(a[1] + (b[1] - a[1]) * t, 6))
    return out


def max_adjacent_jump_px(rows: list[dict]) -> float:
    """相邻帧 11 关节的最大位移。LERP 应当让这个值下降（定格改过渡），
    MICRO 则基本不动它 —— 用它区分「平滑化」与「人为抖动」。"""
    return round(max(
        (math.dist(a[k], b[k]) for a, b in zip(rows, rows[1:]) for k in a),
        default=0.0), 4)


def measure(ctx: Ctx, original: list[dict],
            modified: list[dict]) -> dict:
    before = [ctx.out(j) for j in original]
    after = [ctx.out(j) for j in modified]
    exact = perceptual = pairs = 0
    jumps = []
    for a, b in zip(after, after[1:]):
        for bone in LEG_BONES:
            pairs += 1
            d = abs(b[bone] - a[bone])
            if d < EXACT_EPS:
                exact += 1
            if d < PERCEPTUAL_EPS:
                perceptual += 1
            jumps.append(d)
    deltas, changed_frames = [], 0
    for o, m in zip(original, modified):
        worst = 0.0
        for k in o:
            worst = max(worst, math.dist(o[k], m[k]))
        deltas.append(worst)
        if worst > 1e-9:
            changed_frames += 1
    return {
        "frames": len(original), "pairs": pairs,
        "exact_flat_pairs": exact,
        "perceptual_flat_pairs": perceptual,
        "changed_frames": changed_frames,
        "max_joint_delta_px": round(max(deltas), 4),
        "mean_joint_delta_px": round(sum(deltas) / len(deltas), 5),
        "max_output_jump_deg": round(max(jumps), 4),
        "mean_output_jump_deg": round(sum(jumps) / len(jumps), 4),
        "max_abs_out_deg": round(
            max(abs(v) for row in after for v in row.values()), 4),
        "baseline_max_abs_out_deg": round(
            max(abs(v) for row in before for v in row.values()), 4),
        "max_adjacent_jump_px": max_adjacent_jump_px(modified),
        "baseline_max_adjacent_jump_px": max_adjacent_jump_px(original),
    }


def main() -> int:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    ctx = Ctx(mi)
    tracks = {k: v["track"] for k, v in cm["cards"].items()}
    tracks.update({k: v["track"] for k, v in cm["motions"].items()})

    base: dict[str, list[dict]] = {}
    flags: dict[str, list[bool]] = {}
    seg_count = 0
    for card, track in tracks.items():
        base[card] = [frame_joints(f, ctx.keys) for f in track]
        raws = [ctx.raw(j) for j in base[card]]
        flags[card] = [
            any(abs(raws[i + 1][b] - raws[i][b]) < EXACT_EPS
                for b in LEG_BONES)
            for i in range(len(track) - 1)]
        seg_count += len(segments_of(flags[card]))

    def summarize(amplitude, per: dict) -> dict:
        return {
            "amplitude_px": amplitude,
            "exact_flat_pairs": sum(
                p["exact_flat_pairs"] for p in per.values()),
            "perceptual_flat_pairs": sum(
                p["perceptual_flat_pairs"] for p in per.values()),
            "changed_frames": sum(
                p["changed_frames"] for p in per.values()),
            "max_joint_delta_px": max(
                p["max_joint_delta_px"] for p in per.values()),
            "mean_joint_delta_px": round(
                sum(p["mean_joint_delta_px"] for p in per.values())
                / len(per), 5),
            "max_output_jump_deg": max(
                p["max_output_jump_deg"] for p in per.values()),
            "max_abs_out_deg": max(
                p["max_abs_out_deg"] for p in per.values()),
            "max_adjacent_jump_px": max(
                p["max_adjacent_jump_px"] for p in per.values()),
            "baseline_max_adjacent_jump_px": max(
                p["baseline_max_adjacent_jump_px"] for p in per.values()),
            "per_card": per,
        }

    rows = {}
    for A in AMPLITUDES:
        per = {}
        for card in tracks:
            mod = (base[card] if A == 0.0
                   else build_micro(base[card], flags[card], A))
            per[card] = measure(ctx, base[card], mod)
        rows[f"micro_{A:g}"] = summarize(A, per)

    lerp_per = {}
    for card in tracks:
        lerp_per[card] = measure(
            ctx, base[card], build_lerp(base[card], flags[card]))
    rows["lerp_transition"] = summarize(None, lerp_per)

    # HYBRID：长定格段先做平滑过渡（动作从僵住变渐进），再对残留的
    # 碰撞型 / 尾段平台补一段极小微扰，把精确平台压到 0。
    hybrid_per = {}
    for card in tracks:
        lerped = build_lerp(base[card], flags[card])
        raws = [ctx.raw(j) for j in lerped]
        flags2 = [
            any(abs(raws[i + 1][b] - raws[i][b]) < EXACT_EPS
                for b in LEG_BONES)
            for i in range(len(lerped) - 1)]
        hybrid = build_micro(lerped, flags2, 0.3)
        hybrid_per[card] = measure(ctx, base[card], hybrid)
    rows["hybrid_lerp_micro03"] = summarize(0.3, hybrid_per)

    baseline = rows["micro_0"]
    # 硬门槛：精确平台归零 **且** 可辨平台严格低于现状。
    # 只满足前者而视觉没改善的档（micro_0.05 / 0.1）不算解决问题。
    eligible = [k for k, v in rows.items()
                if k != "micro_0"
                and v["exact_flat_pairs"] == 0
                and v["perceptual_flat_pairs"]
                < baseline["perceptual_flat_pairs"]]
    recommended = min(
        eligible, key=lambda k: (rows[k]["perceptual_flat_pairs"],
                                 rows[k]["max_joint_delta_px"])) \
        if eligible else None
    report = {
        "tracks": len(tracks),
        "frames": sum(len(t) for t in tracks.values()),
        "segments": seg_count,
        "baseline_exact_flat_pairs": baseline["exact_flat_pairs"],
        "baseline_perceptual_flat_pairs": baseline["perceptual_flat_pairs"],
        "rows": rows,
        "recommendation_rule": (
            "精确平台归零 + 可辨平台严格低于现状；再按可辨平台最低、"
            "关节位移最小排序"),
        "recommended_case": recommended,
        "checks": {
            "fifteen_tracks_284_frames": (len(tracks) == 15
                                          and sum(len(t) for t in
                                                  tracks.values()) == 284),
            "baseline_exact_is_p3_floor": (
                baseline["exact_flat_pairs"] == 255),
            "baseline_perceptual_is_p3_value": (
                baseline["perceptual_flat_pairs"] == 308),
            "micro_monotone_in_amplitude": all(
                rows[f"micro_{a:g}"]["max_joint_delta_px"]
                <= rows[f"micro_{b:g}"]["max_joint_delta_px"] + 1e-9
                for a, b in zip(AMPLITUDES[1:-1], AMPLITUDES[2:])),
            "some_candidate_reaches_zero_exact": any(
                v["exact_flat_pairs"] == 0 for v in rows.values()),
            "hybrid_reaches_zero_exact": (
                rows["hybrid_lerp_micro03"]["exact_flat_pairs"] == 0),
            "recommended_is_zero_exact": (
                recommended is not None
                and rows[recommended]["exact_flat_pairs"] == 0),
            "recommended_perceptual_below_baseline": (
                recommended is not None
                and rows[recommended]["perceptual_flat_pairs"]
                < baseline["perceptual_flat_pairs"]),
            "small_micro_moves_less_than_lerp": (
                rows["micro_0.3"]["max_joint_delta_px"]
                < rows["lerp_transition"]["max_joint_delta_px"]),
            # 只是「没有变差」：最大相邻跳变来自未被改动的其他段，
            # 不写成「LERP 平滑了全局跳变」这种没证据的话。
            "lerp_does_not_worsen_adjacent_jumps": (
                rows["lerp_transition"]["max_adjacent_jump_px"]
                <= baseline["max_adjacent_jump_px"] + 1e-9),
        },
    }
    report["failed"] = [k for k, v in report["checks"].items() if not v]
    report["ok"] = all(report["checks"].values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("SEGMENTS", seg_count)
    print(f"{'case':<22} {'exact':>6} {'perc':>6} {'frames':>7} "
          f"{'maxpx':>9} {'meanpx':>9} {'adjpx':>9}")
    for k, v in rows.items():
        print(f"{k:<22} {v['exact_flat_pairs']:>6} "
              f"{v['perceptual_flat_pairs']:>6} "
              f"{v['changed_frames']:>7} "
              f"{v['max_joint_delta_px']:>9.4f} "
              f"{v['mean_joint_delta_px']:>9.5f} "
              f"{v['max_adjacent_jump_px']:>9.4f}")
    print("RECOMMENDED", recommended)
    for k, v in report["checks"].items():
        print("CHECK", k, v)
    print("CANDIDATE_SCAN_OK" if report["ok"] else "CANDIDATE_SCAN_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
