"""P4 · 实机验收 · 同源帧序列双表复算（纯读盘 + 纯计算）。

跨 Godot 进程整局 RNG 会漂移，本轮两次真跑的终局 HP 就不同，因此
**不做跨进程逐帧像素 A/B**。替代口径（沿用 B 路线已证伪后的做法）：
取 three_d 真跑读回的 (card, frame) 时间序列，在 Python 侧分别按
P4 落地表（shipped）与 P3 原表（rolled_back）复算 13 骨 delta ——
帧序列同源、只有动作表不同，逐帧 A/B 才成立。

判据口径在写脚本时钉死，只有两类：
  ① 结构性：帧在表范围内、复算覆盖全行、引擎读回 delta 对账、
     站架 delta 全 0、SV 重复图由相同 delta 解释、阶段时长在规格内；
  ② 可复算上界：实机 |P4−P3| 不得超过「两版表全量 284 帧静态复算」
     得到的 D_static（实机帧是其子集，必然 ≤）。
连续帧跳变首次在 P4 语境量化，**没有历史外部锚，不设放行线**，只如实
报告分布；结论由数值 + 看图共同给出。

用法：python analyze_live_p4.py
产出：data/live_p4_analysis.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
P4 = HERE.parent / "原生平台P4"
sys.path.insert(0, str(P4))
from p4_math import LEG_BONES, expected_delta, tracks  # noqa: E402

D = HERE / "data"
LIVE = D / "live_p4.json"
OUT = D / "live_p4_analysis.json"
PHASE_SPEC = {"discard": 0.8, "select": 0.8, "reveal": 1.5,
              "resolve": 1.9}
PHASE_TOL = 0.25
HITSTOP_S = 0.24
EXACT_EPS = 1e-6
PERCEPTUAL_EPS = 0.1


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def pct(xs, q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return round(s[i], 4)


@lru_cache(maxsize=None)
def exp(card: str, frame: int, which: str) -> dict:
    return expected_delta(card, frame, which)


def signature(d: dict) -> str:
    return json.dumps({k: round(float(v), 6) for k, v in d.items()},
                      sort_keys=True)


def leg_series(rows: list, side: str, which: str) -> list:
    out = []
    for r in rows:
        st = r[side]
        card, frame = str(st["card"]), int(st["frame"])
        d = exp(card, frame, which)
        if not d:
            continue
        out.append({"idx": r["idx"], "t": r["t"],
                    "turn": r["tk_turn"], "phase": r["tk_phase"],
                    "card": card, "frame": frame,
                    "leg_peak": round(max(abs(d[k]) for k in LEG_BONES), 6),
                    "legs": {k: round(float(d[k]), 6)
                             for k in LEG_BONES},
                    "sig": signature(d)})
    return out


def jump_stats(series: list) -> dict:
    intra, boundary, residuals = [], [], []
    all_jumps = []
    for a, b in zip(series, series[1:]):
        j = round(max(abs(b["legs"][k] - a["legs"][k])
                      for k in LEG_BONES), 6)
        rec = {"idx": b["idx"], "t": b["t"], "jump_deg": j,
               "from": [a["turn"], a["phase"], a["card"], a["frame"]],
               "to": [b["turn"], b["phase"], b["card"], b["frame"]]}
        all_jumps.append(j)
        if a["turn"] == b["turn"] and a["phase"] == b["phase"]:
            intra.append(rec)
        else:
            boundary.append(rec)
        if a["card"] != "stance" and b["card"] == "stance":
            residuals.append({"idx": a["idx"], "t": a["t"],
                              "card": a["card"], "frame": a["frame"],
                              "leg_peak_before_zero": a["leg_peak"]})
    iv = [r["jump_deg"] for r in intra]
    bv = [r["jump_deg"] for r in boundary]
    return {
        "pairs": len(all_jumps),
        "exact_flat_pairs": sum(1 for j in all_jumps if j < EXACT_EPS),
        "perceptual_flat_pairs": sum(
            1 for j in all_jumps if j < PERCEPTUAL_EPS),
        "max_jump_deg": max(all_jumps) if all_jumps else 0.0,
        "p95_jump_deg": pct(all_jumps, 0.95),
        "mean_jump_deg": round(sum(all_jumps) / len(all_jumps), 6)
        if all_jumps else 0.0,
        "intra_count": len(iv),
        "intra_max_deg": max(iv) if iv else 0.0,
        "intra_p95_deg": pct(iv, 0.95),
        "boundary_count": len(bv),
        "boundary_max_deg": max(bv) if bv else 0.0,
        "return_to_stance_events": len(residuals),
        "max_leg_peak_before_zero_deg": max(
            (r["leg_peak_before_zero"] for r in residuals), default=0.0),
        "worst_intra": max(intra, key=lambda r: r["jump_deg"]) if intra
        else None,
        "worst_boundary": max(boundary, key=lambda r: r["jump_deg"])
        if boundary else None,
        "residual_samples": residuals[:8],
    }


def static_upper_bound() -> dict:
    """两版表全量帧上 |P4−P3| 的最大逐骨差，作为实机的可复算上界。"""
    t4, t3 = tracks("shipped"), tracks("rolled_back")
    worst = 0.0
    worst_at = None
    frames = 0
    for card, frames4 in t4.items():
        if card not in t3:
            continue
        n = min(len(frames4), len(t3[card]))
        for fr in range(n):
            a = exp(card, fr, "shipped")
            b = exp(card, fr, "rolled_back")
            if not a or not b:
                continue
            d = max(abs(a[k] - b[k]) for k in a)
            frames += 1
            if d > worst:
                worst = d
                worst_at = [card, fr]
    return {"frames_compared": frames,
            "max_abs_delta_diff_deg": round(worst, 6),
            "worst_at": worst_at}


def phase_durations(payload: dict) -> dict:
    ch = [c for c in payload["phase_changes"]
          if c["kind"] == "tk_phase"]
    out = {}
    for i, c in enumerate(ch):
        turn, ph = c["value"].split(":", 1)
        end = ch[i + 1]["t"] if i + 1 < len(ch) else payload["total_t"]
        out.setdefault(turn, {})[ph] = round(end - c["t"], 3)
    return out


def main() -> int:
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    cases = live["cases"]
    rows = cases["three_d"]["payload"]["rows"]
    p3 = cases["three_d"]["payload"]
    off = cases["default_off"]["payload"]

    upstream_ok = (
        isinstance(live.get("checks"), dict) and bool(live["checks"])
        and all(v is True for v in live["checks"].values())
        and not live.get("failed") and live.get("ok") is True)

    # ── 实机帧是否都落在两版表的 track 范围内 ──
    t4, t3 = tracks("shipped"), tracks("rolled_back")
    out_of_range = []
    for r in rows:
        for side in ("player", "foe"):
            st = r[side]
            card, fr = str(st["card"]), int(st["frame"])
            if card in ("stance", ""):
                continue
            if card not in t4 or card not in t3:
                out_of_range.append((r["idx"], side, card, fr, "no_card"))
                continue
            if fr < 0 or fr >= len(t4[card]) or fr >= len(t3[card]):
                out_of_range.append((r["idx"], side, card, fr, "bad_frame"))

    # ── 引擎读回 delta 与 shipped 复算逐骨对账（独立复核 runner 的结论）──
    engine_bad = []
    for r in rows:
        for side in ("player", "foe"):
            st = r[side]
            got = st.get("delta", {})
            want = exp(str(st["card"]), int(st["frame"]), "shipped")
            if not want or not got:
                engine_bad.append((r["idx"], side, "missing"))
                continue
            worst = max(abs(float(got.get(k, 1e9)) - want[k])
                        for k in want)
            if worst > 1e-3:
                engine_bad.append((r["idx"], side, round(worst, 6)))

    # ── 同源双表曲线与跳变 ──
    curves = {s: {"p3": leg_series(rows, s, "rolled_back"),
                  "p4": leg_series(rows, s, "shipped")}
              for s in ("player", "foe")}
    jumps = {s: {"p3": jump_stats(curves[s]["p3"]),
                 "p4": jump_stats(curves[s]["p4"])}
             for s in ("player", "foe")}
    extra = {}
    for s in ("player", "foe"):
        a, b = curves[s]["p3"], curves[s]["p4"]
        recs = []
        for x, y in zip(zip(a, a[1:]), zip(b, b[1:])):
            j3 = max(abs(x[1]["legs"][k] - x[0]["legs"][k])
                     for k in LEG_BONES)
            j4 = max(abs(y[1]["legs"][k] - y[0]["legs"][k])
                     for k in LEG_BONES)
            recs.append({"idx": y[1]["idx"], "t": y[1]["t"],
                         "p3": round(j3, 6), "p4": round(j4, 6),
                         "extra": round(j4 - j3, 6)})
        vals = [r["extra"] for r in recs]
        diffs = [max(abs(y["legs"][k] - x["legs"][k])
                     for k in LEG_BONES)
                 for x, y in zip(a, b)]
        extra[s] = {
            "pairs": len(recs),
            "max_extra_jump_deg": max(vals) if vals else 0.0,
            "min_extra_jump_deg": min(vals) if vals else 0.0,
            "p95_extra_jump_deg": pct(vals, 0.95),
            "mean_extra_jump_deg": round(sum(vals) / len(vals), 6)
            if vals else 0.0,
            "max_abs_delta_diff_deg": round(max(diffs), 6)
            if diffs else 0.0,
            "worst_extra_pair": max(recs, key=lambda r: r["extra"])
            if recs else None,
            "worst_delta_pair": None,
        }
        if diffs:
            i = max(range(len(diffs)), key=lambda k: diffs[k])
            extra[s]["worst_delta_pair"] = {
                "idx": b[i]["idx"], "t": b[i]["t"],
                "card": b[i]["card"], "frame": b[i]["frame"],
                "diff_deg": round(diffs[i], 6)}
        for which, j in (("p3", jumps[s]["p3"]), ("p4", jumps[s]["p4"])):
            peaks = [p["leg_peak"] for p in curves[s][which]]
            j["peak_mean_deg"] = round(sum(peaks) / len(peaks), 6)
            j["peak_max_deg"] = max(peaks) if peaks else 0.0

    bound = static_upper_bound()
    live_max_diff = max(extra[s]["max_abs_delta_diff_deg"]
                        for s in extra)

    # ── 站架帧 delta 全 0（两版表都应如此）──
    stance_bad = []
    for r in rows:
        for s in ("player", "foe"):
            st = r[s]
            if str(st["card"]) != "stance":
                continue
            for which in ("shipped", "rolled_back"):
                d = exp("stance", 0, which)
                if not d or any(abs(v) > 1e-6 for v in d.values()):
                    stance_bad.append((r["idx"], s, which))

    # ── SV 重复图必须由相同 13 骨 delta 解释，而不是停滞帧缓冲 ──
    groups = defaultdict(list)
    for r in rows:
        p = r.get("player_sv")
        if p and Path(p).is_file():
            groups[sha(Path(p))].append(
                (r["idx"], str(r["player"]["card"]),
                 int(r["player"]["frame"])))
    mixed = []
    for h, items in groups.items():
        sigs = {signature(exp(c, f, "shipped")) for _, c, f in items}
        if len(sigs) > 1:
            mixed.append({"sha": h[:12], "count": len(items),
                          "distinct_delta": len(sigs)})
    sv_channel = {
        "total": sum(len(v) for v in groups.values()),
        "unique_sha": len(groups),
        "groups_with_mixed_delta": mixed,
        "largest_group": max((len(v) for v in groups.values()),
                             default=0),
    }

    # ── 阶段时长（沿用 B 路线口径：hitstop + turn1 discard 排除）──
    dur = {"three_d": phase_durations(p3),
           "default_off": phase_durations(off)}
    winners = {}
    for tag, payload in (("three_d", p3), ("default_off", off)):
        w = {}
        for r in payload["rows"]:
            if r["tk_phase"] == "resolve":
                w[str(r["tk_turn"])] = r["tk_winner"]
        winners[tag] = w
    effective_spec, dur_bad = {}, []
    for tag, by_turn in dur.items():
        for turn, phases in by_turn.items():
            win = winners[tag].get(turn, "")
            hitstop = 0.0 if win in ("", "draw") else HITSTOP_S
            spec = dict(PHASE_SPEC)
            spec["resolve"] += hitstop
            effective_spec.setdefault(tag, {})[turn] = {
                "winner": win, "hitstop_s": hitstop,
                "resolve_spec_s": round(spec["resolve"], 3)}
            for ph, want in spec.items():
                if turn == "1" and ph == "discard":
                    continue
                got = phases.get(ph)
                if got is None or abs(got - want) > PHASE_TOL:
                    dur_bad.append((tag, turn, ph, got, round(want, 3)))

    # ── 两次真跑牌局指纹（只记录，不做逐帧 A/B）──
    outcomes = {tag: {"final_hp": cases[tag]["payload"]["final_hp"],
                      "final_wins": cases[tag]["payload"]["final_wins"]}
                for tag in cases}
    distinct = len({json.dumps(v, sort_keys=True)
                    for v in outcomes.values()})

    checks = {
        "upstream_run_all_checks_true": upstream_ok,
        "all_live_frames_in_track_range": not out_of_range,
        "delta_recomputed_for_all_rows_both_tables": all(
            len(curves[s][w]) == len(rows)
            for s in curves for w in ("p3", "p4")),
        "engine_delta_matches_shipped_recomputation": not engine_bad,
        "static_upper_bound_positive_and_recomputed": (
            bound["frames_compared"] >= 284
            and bound["max_abs_delta_diff_deg"] > 0.0),
        "live_delta_diff_within_static_bound": (
            live_max_diff <= bound["max_abs_delta_diff_deg"] + 1e-6),
        "exact_flat_pairs_not_worse_in_live": all(
            jumps[s]["p4"]["exact_flat_pairs"]
            <= jumps[s]["p3"]["exact_flat_pairs"] for s in jumps),
        "stance_delta_zero_both_tables": not stance_bad,
        "sv_duplicates_explained_by_delta": (
            sv_channel["total"] > 0 and not mixed),
        "phase_durations_within_spec": not dur_bad,
        # 牌局指纹是否一致是「前提检验」，不是放行判据：无论两局是否
        # 碰巧同结局，都明确钉死「不做跨进程逐帧像素 A/B」并留理由。
        "framewise_pixel_ab_explicitly_not_applicable": (
            live["preconditions"]["framewise_pixel_ab_applicable"] is False
            and "RNG" in live["preconditions"]["note"]),
        "extra_jump_distribution_recorded": all(
            extra[s]["pairs"] == len(rows) - 1
            and isinstance(extra[s]["max_extra_jump_deg"], float)
            for s in extra),
    }

    report = {
        "source": "data/live_p4.json",
        "frame_source": "three_d live run (same card/frame for both tables)",
        "sample_count": len(rows), "sample_s": live["sample_s"],
        "threshold_policy": (
            "连续帧跳变首次在 P4 语境量化，无历史外部锚，不设放行线；"
            "只报告分布，结论结合看图给出。唯一数值上界 D_static 由两版表"
            "全量 284 帧独立复算得到，不是拍脑袋阈值。"),
        "match_outcomes": outcomes,
        "distinct_match_outcomes": distinct,
        "static_bound": bound,
        "live_max_abs_delta_diff_deg": live_max_diff,
        "curves": {s: {w: curves[s][w] for w in ("p3", "p4")}
                   for s in curves},
        "jump_stats": jumps,
        "homologous_extra": extra,
        "phase_durations": dur,
        "phase_spec_s": PHASE_SPEC, "phase_tol_s": PHASE_TOL,
        "effective_phase_spec": effective_spec,
        "phase_duration_exclusions": [
            "turn 1 discard: recorded during intro (3.75s intro included)",
            "non-draw turns add HITSTOP_S=0.24 to resolve wall time"],
        "phase_duration_violations": dur_bad,
        "capture_channel": {"sv": sv_channel},
        "out_of_range_frames": out_of_range,
        "engine_delta_mismatches": engine_bad,
        "stance_violations": stance_bad,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("OUTCOMES", outcomes, "distinct", distinct)
    print("STATIC_BOUND", bound, "live_max_diff", live_max_diff)
    for s in ("player", "foe"):
        for w in ("p3", "p4"):
            j = jumps[s][w]
            print("JUMP", s, w, "exact", j["exact_flat_pairs"],
                  "perceptual", j["perceptual_flat_pairs"],
                  "max", j["max_jump_deg"], "p95", j["p95_jump_deg"],
                  "intra_max", j["intra_max_deg"],
                  "boundary_max", j["boundary_max_deg"],
                  "peak_mean", j["peak_mean_deg"])
        e = extra[s]
        print("EXTRA", s, "max", e["max_extra_jump_deg"],
              "min", e["min_extra_jump_deg"],
              "p95", e["p95_extra_jump_deg"],
              "mean", e["mean_extra_jump_deg"],
              "max_delta_diff", e["max_abs_delta_diff_deg"])
    print("SV", sv_channel)
    print("PHASE_VIOLATIONS", dur_bad)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LIVE_P4_ANALYSIS_OK" if report["ok"]
          else "LIVE_P4_ANALYSIS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
