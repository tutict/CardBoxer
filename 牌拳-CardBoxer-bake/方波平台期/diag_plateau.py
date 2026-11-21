"""P3 · 方波平台期诊断（纯读盘 + 纯计算，不改任何文件）。

要回答的问题（先诊断再动手，不凭印象选方案）：

  Q1 时间线上腿峰值「钉在 9° 不动」的方波，成因是
     ① 硬 clamp 把不同的原始信号削成同一个值，还是
     ② 2D 动作表里本来就有连续相同的平台帧？
     这两者的解法完全不同：① 换映射即可，② 换映射救不了，
     得改动作表或加时间插值。
  Q2 若换无状态的软限幅映射，平台率能降多少、幅度与最大角代价多大？
  Q3 在 B 路线真实对局的帧序列上，方波段有多长，新映射是否真的
     让曲线「动起来」？

候选映射全部按「运行时可实现性」分组：
  * stateless —— 只改 rig_driver.gd::retarget_delta 的腿骨 4 行，
    不需要 card 上下文，旧 mapping 可加默认值兼容；
  * contextual —— 需要 per-track 峰值（逐轨归一化），要改
    retarget_delta 签名或预计算表，成本高，仅作上限参照。

用法：python diag_plateau.py
产出：data/plateau_diagnosis.json
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
LIVE = BAKE / "实跑一局" / "data" / "live_match.json"
OUT = HERE / "data" / "plateau_diagnosis.json"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
EXACT_EPS = 1e-6          # 逐值完全相同
PERCEPTUAL_EPS = 0.1      # 0.1° 以下视为视觉不可辨


def hard(x: float, cap: float) -> float:
    return max(-cap, min(cap, x))


def soft_tanh(x: float, cap: float) -> float:
    return cap * math.tanh(x / cap)


def soft_atan(x: float, cap: float) -> float:
    """atan 软限幅：初始斜率 1，渐近 ±cap，但按 1/x 慢衰减。

    tanh 的尾部是指数衰减（raw 一超过 3cap 就几乎恒等 cap），
    atan 的尾部是 1/x，在 36°..116° 区间仍有可分辨的变化，
    这是它比 P2 研究过的 tanh 更适合消平台的原因。
    """
    return cap * (2.0 / math.pi) * math.atan((math.pi / 2.0) * x / cap)


def soft_log(x: float, cap: float, s: float, ref: float) -> float:
    """无上界对数压缩，把 ref 处归一化到 cap；ref 是固定常数，无状态。"""
    if x == 0.0:
        return 0.0
    denom = math.log1p(ref / s)
    return math.copysign(cap * math.log1p(abs(x) / s) / denom, x)


MAPPINGS = {
    "hard09": ("stateless", lambda x: hard(x, 9.0)),
    "hard12": ("stateless", lambda x: hard(x, 12.0)),
    "tanh09": ("stateless", lambda x: soft_tanh(x, 9.0)),
    "tanh12": ("stateless", lambda x: soft_tanh(x, 12.0)),
    "atan09": ("stateless", lambda x: soft_atan(x, 9.0)),
    "atan12": ("stateless", lambda x: soft_atan(x, 12.0)),
    "atan15": ("stateless", lambda x: soft_atan(x, 15.0)),
    "log09": ("stateless", lambda x: soft_log(x, 9.0, 9.0, 116.0986)),
    "log12": ("stateless", lambda x: soft_log(x, 12.0, 9.0, 116.0986)),
}


def pct(xs, q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return round(s[i], 4)


def mean(xs) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def longest_flat_run(vals: list[float], eps: float) -> int:
    best = run = 1
    for a, b in zip(vals, vals[1:]):
        run = run + 1 if abs(b - a) < eps else 1
        best = max(best, run)
    return best


def evaluate(name: str, fn, raw_by_track: dict,
             contextual: dict | None = None) -> dict:
    """对每轨每骨算输出序列，统计平台 / 幅度 / 跳变。"""
    all_abs, all_jump = [], []
    exact_flat = perceptual_flat = pairs = 0
    native_exact = clamp_exact = 0
    native_perc = clamp_perc = 0
    runs, distinct_ratios = [], []
    for card, bones in raw_by_track.items():
        for bone, raw in bones.items():
            if contextual is None:
                out = [fn(x) for x in raw]
            else:
                peak = contextual[card]
                out = [fn(x, peak) for x in raw]
            all_abs.extend(abs(v) for v in out)
            jumps = [abs(b - a) for a, b in zip(out, out[1:])]
            all_jump.extend(jumps)
            for i, j in enumerate(jumps):
                pairs += 1
                raw_same = abs(raw[i + 1] - raw[i]) < EXACT_EPS
                if j < EXACT_EPS:
                    exact_flat += 1
                    if raw_same:
                        native_exact += 1
                    else:
                        clamp_exact += 1
                if j < PERCEPTUAL_EPS:
                    perceptual_flat += 1
                    if raw_same:
                        native_perc += 1
                    else:
                        clamp_perc += 1
            runs.append(longest_flat_run(out, EXACT_EPS))
            distinct_ratios.append(
                len({round(v, 6) for v in out}) / max(1, len(out)))
    return {
        "kind": MAPPINGS.get(name, ("contextual", None))[0],
        "pairs": pairs,
        "exact_flat_pairs": exact_flat,
        "exact_flat_ratio": round(exact_flat / pairs, 4),
        "exact_flat_from_native_track": native_exact,
        "exact_flat_from_mapping": clamp_exact,
        "perceptual_flat_pairs": perceptual_flat,
        "perceptual_flat_ratio": round(perceptual_flat / pairs, 4),
        "perceptual_flat_from_native_track": native_perc,
        "perceptual_flat_from_mapping": clamp_perc,
        "longest_exact_flat_run_frames": max(runs),
        "mean_distinct_ratio_per_track_bone": mean(distinct_ratios),
        "mean_abs_deg": mean(all_abs),
        "p95_abs_deg": pct(all_abs, 0.95),
        "max_abs_deg": round(max(all_abs), 4),
        "max_intra_jump_deg": round(max(all_jump), 4),
        "p95_intra_jump_deg": pct(all_jump, 0.95),
        "mean_intra_jump_deg": mean(all_jump),
    }


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
    chain = mi["chain"]
    # 让 retarget_delta 返回未经 clamp 的原始腿角
    mapping = dict(mi["mapping"])
    mapping["leg_cap_deg"] = 1e9

    raw_by_track: dict[str, dict[str, list[float]]] = {}
    for card, track in tracks.items():
        raw_by_track[card] = {b: [] for b in LEG_BONES}
        for frame in track:
            fj = {k: tuple(frame[k]) for k in keys}
            _d, raw = retarget_delta(fj, stance_j, chain, mapping,
                                     stance_points)
            for b in LEG_BONES:
                raw_by_track[card][b].append(float(raw[b]))
    all_raw = [x for bones in raw_by_track.values()
               for seq in bones.values() for x in seq]
    abs_raw = [abs(x) for x in all_raw]
    contextual = {c: max((abs(x) for seq in bones.values()
                          for x in seq), default=1.0)
                  for c, bones in raw_by_track.items()}

    results = {name: evaluate(name, fn, raw_by_track)
               for name, (_kind, fn) in MAPPINGS.items()}
    # contextual 上限参照：逐轨峰值归一化到 9°，理论上平台最少
    norm9 = evaluate("norm09", lambda x, peak: 9.0 * x / peak,
                     raw_by_track, contextual)
    norm9["kind"] = "contextual"
    results["norm09_track_peak"] = norm9

    # Q1：现状 hard09 的平台成因拆分
    h = results["hard09"]
    q1 = {
        "shipped_cap_deg": 9.0,
        "exact_flat_pairs": h["exact_flat_pairs"],
        "exact_flat_from_native_track": h["exact_flat_from_native_track"],
        "exact_flat_from_clamp": h["exact_flat_from_mapping"],
        "clamp_share_of_exact_flat": round(
            h["exact_flat_from_mapping"]
            / max(1, h["exact_flat_pairs"]), 4),
        "perceptual_flat_pairs": h["perceptual_flat_pairs"],
        "perceptual_flat_from_clamp": h["perceptual_flat_from_mapping"],
        "clamp_share_of_perceptual_flat": round(
            h["perceptual_flat_from_mapping"]
            / max(1, h["perceptual_flat_pairs"]), 4),
    }

    # Q3：B 路线真实对局帧序列上的曲线（同源，只换映射）
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    rows = live["cases"]["cap9"]["payload"]["rows"]
    curves = {}
    for name, (_kind, fn) in MAPPINGS.items():
        if name not in ("hard09", "tanh12", "atan12", "atan15"):
            continue
        series, card_tags = [], []
        for r in rows:
            st = r["player"]
            card, frame = str(st["card"]), int(st["frame"])
            card_tags.append(card)
            if card == "stance":
                # 站架不在 15 轨动作表里，它的 raw 恒为 0
                series.append(0.0)
                continue
            if card not in raw_by_track or frame >= len(
                    raw_by_track[card]["thigh_f"]):
                series.append(0.0)
                continue
            vals = [fn(raw_by_track[card][b][frame]) for b in LEG_BONES]
            series.append(round(max(abs(v) for v in vals), 4))
        flat_pairs = sum(abs(b - a) < EXACT_EPS
                         for a, b in zip(series, series[1:]))
        # 站架段（全程 0）本来就该平，不能算「动作平台」；
        # 只统计相邻两点都处于动作卡内的对。
        action_pairs = [(a, b) for i, (a, b) in enumerate(
            zip(series, series[1:]))
            if card_tags[i] != "stance" and card_tags[i + 1] != "stance"]
        action_flat = sum(abs(b - a) < EXACT_EPS for a, b in action_pairs)
        action_run, run = 0, 0
        for i, (a, b) in enumerate(zip(series, series[1:])):
            if card_tags[i] == "stance" or card_tags[i + 1] == "stance":
                run = 0
                continue
            run = run + 1 if abs(b - a) < EXACT_EPS else 0
            action_run = max(action_run, run)
        curves[name] = {
            "samples": len(series),
            "exact_flat_adjacent_pairs": flat_pairs,
            "longest_flat_run": longest_flat_run(series, EXACT_EPS),
            "action_pairs": len(action_pairs),
            "action_exact_flat_pairs": action_flat,
            "longest_action_flat_run_pairs": action_run,
            "mean_peak_deg": mean(series),
            "max_peak_deg": max(series),
            "distinct_values": len(set(series)),
        }

    # 判据只钉结构性事实，不设「凭结果调」的放行阈值。
    # 首版曾写 clamp_is_major_cause > 0.5 与 reduces_plateau < 50%，
    # 两条都按想象设阈值；实测成因接近对半、且软映射已打到原生平台下限
    # （255 对是动作表本身重复帧，任何无状态映射都消不掉），遂订正。
    native = h["exact_flat_from_native_track"]
    atan_names = ("atan09", "atan12", "atan15")
    checks = {
        "fifteen_tracks": len(tracks) == 15,
        "frames_284": sum(len(t) for t in tracks.values()) == 284,
        "raw_distribution_matches_p2": (
            abs(mean(abs_raw) - 10.1991) < 0.01
            and abs(pct(abs_raw, 0.95) - 34.9608) < 0.01),
        "shipped_hard09_has_plateau": h["exact_flat_pairs"] > 0,
        "both_causes_sum_to_total": (
            native + h["exact_flat_from_mapping"]
            == h["exact_flat_pairs"]),
        "both_causes_are_material": (
            native > 0 and h["exact_flat_from_mapping"] > 0),
        "soft_mapping_removes_every_clamp_flat_pair": all(
            results[n]["exact_flat_from_mapping"] == 0
            for n in atan_names),
        "soft_mapping_reaches_native_track_floor": all(
            results[n]["exact_flat_pairs"] == native for n in atan_names),
        "contextual_norm_cannot_beat_stateless": (
            norm9["exact_flat_pairs"] == native),
        "soft_mapping_shortens_longest_flat_run": all(
            results[n]["longest_exact_flat_run_frames"]
            < h["longest_exact_flat_run_frames"] for n in atan_names),
        "soft_mapping_improves_perceptual_flatness": all(
            results[n]["perceptual_flat_pairs"]
            < h["perceptual_flat_pairs"] for n in atan_names),
        "atan_beats_tanh_on_perceptual_flatness": (
            results["atan12"]["perceptual_flat_pairs"]
            < results["tanh12"]["perceptual_flat_pairs"]),
        "stateless_mapping_keeps_max_angle_bounded": all(
            results[n]["max_abs_deg"] <= 15.0
            for n in (*atan_names, "tanh09", "tanh12")),
        "live_curves_from_real_match": all(
            c["samples"] == len(rows) for c in curves.values()),
        "live_action_plateau_reduced": all(
            curves[n]["action_exact_flat_pairs"]
            < curves["hard09"]["action_exact_flat_pairs"]
            for n in ("tanh12", "atan12", "atan15")),
        "live_distinct_values_increased": all(
            curves[n]["distinct_values"]
            > curves["hard09"]["distinct_values"]
            for n in ("tanh12", "atan12", "atan15")),
    }
    report = {
        "source": {
            "motion_input": str(GAME / "data" / "motion_input.json"),
            "card_motion": str(GAME / "data" / "card_motion.json"),
            "live_match": str(LIVE),
        },
        "eps": {"exact_deg": EXACT_EPS, "perceptual_deg": PERCEPTUAL_EPS},
        "raw_abs_deg": {"n": len(all_raw), "mean": mean(abs_raw),
                        "p95": pct(abs_raw, 0.95),
                        "max": round(max(abs_raw), 4)},
        "q1_cause": q1,
        "mappings": results,
        "contextual_track_peaks_deg": {
            k: round(v, 4) for k, v in contextual.items()},
        "live_match_curves": curves,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("RAW", report["raw_abs_deg"])
    print("Q1_CAUSE", q1)
    for n, r in results.items():
        print("MAP", n, r["kind"],
              "exact_flat", r["exact_flat_pairs"],
              f"({r['exact_flat_ratio']})",
              "perc_flat", r["perceptual_flat_pairs"],
              "longest_run", r["longest_exact_flat_run_frames"],
              "mean_abs", r["mean_abs_deg"],
              "max_abs", r["max_abs_deg"],
              "max_jump", r["max_intra_jump_deg"],
              "distinct", r["mean_distinct_ratio_per_track_bone"])
    print("LIVE_CURVES", json.dumps(curves, ensure_ascii=False))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PLATEAU_DIAG_OK" if report["ok"] else "PLATEAU_DIAG_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
