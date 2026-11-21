"""B 路线 · 真实对局节奏与动作连贯性分析（纯读盘 + 纯计算）。

由于跨 Godot 进程的整局 RNG 会漂移（即使固定 seed），两次运行的牌局
不同，**逐帧像素 A/B 的前提不成立**。替代口径：取 cap9 局真实跑出来的
(card, frame) 时间序列，在 Python 侧用同一份动作表分别按 cap3 / cap9
复算 delta —— 帧序列同源、只有幅度档不同，这样逐帧 A/B 才成立。

本脚本只报告事实与分布，不设放行阈值：连续帧跳变是首次量化，没有
历史外部锚，不拿它当放行线（放行线在 verify_live.py 里按可复算的
结构性判据钉死）。阈值口径如实写进验证记录。

用法：python analyze_live.py
产出：data/live_analysis.json
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_live_match import LEG_BONES, expected_delta, fingerprint  # noqa: E402

D = HERE / "data"
LIVE = D / "live_match.json"
FIRST_RUN_LOG = HERE / "logs" / "live_cap9.out"
OUT = D / "live_analysis.json"
PHASE_SPEC = {"discard": 0.8, "select": 0.8, "reveal": 1.5,
              "resolve": 1.9}
PHASE_TOL = 0.25


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def pct(xs, q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return round(s[i], 4)


def delta_signature(card: str, frame: int, cap: float) -> str:
    """同一 sha 的 SV 图必须对应同一份 retarget 后的 13 骨 delta。

    渲染取决于 delta，不取决于 2D 原始关节坐标：实测 focus 5..12 的
    原始 track 逐值不同，但被 clamp 削平后 13 骨 delta 完全相同；
    stance / focus 0 / hit_light 0 的 delta 则全为 0。拿原始关节数据
    做分组口径会把这两种正常情况误报成「渲染停滞」。
    """
    d = expected_delta(card, frame, cap)
    if not d:
        return "missing"
    return json.dumps({k: round(float(v), 6) for k, v in d.items()},
                      sort_keys=True)


def leg_series(rows: list, side: str, cap: float) -> list:
    out = []
    for r in rows:
        st = r[side]
        d = expected_delta(str(st["card"]), int(st["frame"]), cap)
        if not d:
            continue
        out.append({"idx": r["idx"], "t": r["t"],
                    "turn": r["tk_turn"], "phase": r["tk_phase"],
                    "card": str(st["card"]), "frame": int(st["frame"]),
                    "leg_peak": round(max(abs(d[k]) for k in LEG_BONES), 4),
                    "legs": {k: round(float(d[k]), 4)
                             for k in LEG_BONES}})
    return out


def jump_stats(series: list) -> dict:
    intra, boundary, residuals = [], [], []
    for a, b in zip(series, series[1:]):
        j = round(max(abs(b["legs"][k] - a["legs"][k])
                      for k in LEG_BONES), 4)
        rec = {"idx": b["idx"], "t": b["t"], "jump_deg": j,
               "from": [a["turn"], a["phase"], a["card"], a["frame"]],
               "to": [b["turn"], b["phase"], b["card"], b["frame"]]}
        if a["turn"] == b["turn"] and a["phase"] == b["phase"]:
            intra.append(rec)
        else:
            boundary.append(rec)
        # 归零残差：从有动作切回 stance 之前那一帧的腿峰值
        if a["card"] != "stance" and b["card"] == "stance":
            residuals.append({"idx": a["idx"], "t": a["t"],
                              "card": a["card"], "frame": a["frame"],
                              "leg_peak_before_zero": a["leg_peak"]})
    iv = [r["jump_deg"] for r in intra]
    bv = [r["jump_deg"] for r in boundary]
    return {
        "intra_count": len(iv),
        "intra_max_deg": max(iv) if iv else 0.0,
        "intra_p95_deg": pct(iv, 0.95),
        "intra_mean_deg": round(sum(iv) / len(iv), 4) if iv else 0.0,
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
    cap9 = cases["cap9"]["payload"]
    cap3 = cases["cap3"]["payload"]
    rows9, rows3 = cap9["rows"], cap3["rows"]

    # ── 可复现性：第一次单跑 cap9 的 FP vs 本轮 cap9 / cap3 ──
    first_fp = None
    for ln in FIRST_RUN_LOG.read_text(encoding="utf-8").splitlines():
        if ln.startswith("FP cap9 "):
            first_fp = ast.literal_eval(ln[len("FP cap9 "):])
            break
    fps = {"first_solo_cap9": first_fp,
           "ab_cap9": fingerprint(cap9), "ab_cap3": fingerprint(cap3)}
    distinct = {json.dumps(v, sort_keys=True, ensure_ascii=False)
                for v in fps.values() if v is not None}
    reproducibility = {
        "seed": live["seed"],
        "runs_compared": len([v for v in fps.values() if v is not None]),
        "distinct_match_outcomes": len(distinct),
        "seed_makes_match_reproducible": len(distinct) == 1,
        "framewise_pixel_ab_applicable": len(distinct) == 1,
        "note": ("即使 seed() 固定，跨进程整局牌局仍漂移；逐帧像素 A/B "
                 "前提不成立，改用同源帧序列的公式复算 A/B。"),
        "fingerprints": fps,
    }

    # ── 阶段时长 ──
    dur = {tag: phase_durations(cases[tag]["payload"])
           for tag in ("cap9", "cap3")}
    # 口径订正（不是放宽阈值）：
    #  ① 第 1 回 discard 的 phase_change 在 intro 阶段就记下了，
    #     其时长含 3.75 s intro，不是 tk_bot 推进的 0.8 s，按口径排除；
    #  ② 非平局回有 KOF 式命中停顿 HITSTOP_S=0.24，_process 的
    #     hitstop 分支不跑 _tick_taikou，tk_phase_time 冻结，
    #     所以 resolve 的墙钟时长 = 1.9 + 0.24；平局回不启节奏时钟，
    #     没有 hitstop，仍是 1.9。实测平局回 1.97~2.01、非平局
    #     2.22~2.24，正好对上。
    HITSTOP_S = 0.24
    winners = {}
    for tag in ("cap9", "cap3"):
        w = {}
        for r in cases[tag]["payload"]["rows"]:
            if r["tk_phase"] == "resolve":
                w[str(r["tk_turn"])] = r["tk_winner"]
        winners[tag] = w
    effective_spec = {}
    dur_bad = []
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
                    dur_bad.append((tag, turn, ph, got,
                                    round(want, 3)))

    # ── 四态覆盖（cap9 真实局） ──
    states = {
        "reveal_focus": any(r["tk_phase"] == "reveal"
                            and r["player"]["card"] == "focus"
                            and r["foe"]["card"] == "focus" for r in rows9),
        "winner_attack": any(r["tk_phase"] == "resolve" and (
            (r["player"]["card"] not in ("stance",)
             and not r["player"]["card"].startswith("hit_"))
            or (r["foe"]["card"] not in ("stance",)
                and not r["foe"]["card"].startswith("hit_")))
            for r in rows9),
        "loser_react": any(r["tk_phase"] == "resolve" and (
            r["player"]["card"].startswith("hit_")
            or r["foe"]["card"].startswith("hit_")) for r in rows9),
        "draw_both_react": any(
            r["tk_phase"] == "resolve" and r["tk_winner"] == "draw"
            and r["player"]["card"].startswith("hit_")
            and r["foe"]["card"].startswith("hit_") for r in rows9),
    }
    react_rows = [(r["idx"], r["tk_turn"], r["player"]["card"],
                   r["foe"]["card"]) for r in rows9
                  if r["tk_phase"] == "resolve"
                  and (r["player"]["card"].startswith("hit_")
                       or r["foe"]["card"].startswith("hit_"))]

    # ── 同源逐帧 A/B：同一 (card,frame) 序列，只换 cap ──
    curves = {}
    for side in ("player", "foe"):
        curves[side] = {
            "cap3": leg_series(rows9, side, 3.0),
            "cap9": leg_series(rows9, side, 9.0),
        }
    jumps = {side: {"cap3": jump_stats(curves[side]["cap3"]),
                    "cap9": jump_stats(curves[side]["cap9"])}
             for side in ("player", "foe")}
    for side in ("player", "foe"):
        a = jumps[side]["cap3"]
        b = jumps[side]["cap9"]
        peaks3 = [p["leg_peak"] for p in curves[side]["cap3"]]
        peaks9 = [p["leg_peak"] for p in curves[side]["cap9"]]
        a["peak_mean_deg"] = round(sum(peaks3) / len(peaks3), 4)
        b["peak_mean_deg"] = round(sum(peaks9) / len(peaks9), 4)
        a["peak_max_deg"] = max(peaks3)
        b["peak_max_deg"] = max(peaks9)
        b["intra_max_over_cap3"] = round(
            b["intra_max_deg"] / a["intra_max_deg"], 4
        ) if a["intra_max_deg"] > 0 else None
        b["peak_mean_over_cap3"] = round(
            b["peak_mean_deg"] / a["peak_mean_deg"], 4
        ) if a["peak_mean_deg"] > 0 else None

    # ── 截图通道健全性 ──
    live_shas = {}
    for tag in ("cap9", "cap3"):
        paths = [Path(r["live"]) for r in cases[tag]["payload"]["rows"]
                 if r.get("live") and Path(r["live"]).is_file()]
        live_shas[tag] = {"total": len(paths),
                          "unique": len({sha(p) for p in paths})}
    sv_groups = {}
    for tag, cap in (("cap9", 9.0), ("cap3", 3.0)):
        groups = defaultdict(list)
        for r in cases[tag]["payload"]["rows"]:
            p = r.get("player_sv")
            if not p or not Path(p).is_file():
                continue
            groups[sha(Path(p))].append(
                (r["idx"], r["player"]["card"], r["player"]["frame"]))
        bad = []
        for h, items in groups.items():
            sigs = {delta_signature(c, f, cap) for _, c, f in items}
            if len(sigs) > 1:
                bad.append({"sha": h[:12], "count": len(items),
                            "distinct_delta": len(sigs)})
        sv_groups[tag] = {
            "total": sum(len(v) for v in groups.values()),
            "unique_sha": len(groups),
            "groups_with_mixed_delta": bad,
            "largest_group": max((len(v) for v in groups.values()),
                                 default=0),
        }

    checks = {
        "three_turns_each": all(
            len(v) == 3 for v in live["phase_sequences"].values()),
        "phase_durations_within_spec": not dur_bad,
        "four_motion_states_covered": all(states.values()),
        "delta_formula_recomputed_for_both_caps": all(
            len(curves[s][c]) == len(rows9) for s in curves for c in
            ("cap3", "cap9")),
        "live_frames_all_unique": all(
            v["total"] > 0 and v["total"] == v["unique"]
            for v in live_shas.values()),
        "sv_duplicates_all_explained_by_delta": all(
            not v["groups_with_mixed_delta"]
            for v in sv_groups.values()),
        "reproducibility_recorded": (
            reproducibility["runs_compared"] >= 3),
    }
    report = {
        "source": "data/live_match.json",
        "reproducibility": reproducibility,
        "phase_durations": dur,
        "phase_spec_s": PHASE_SPEC, "phase_tol_s": PHASE_TOL,
        "effective_phase_spec": effective_spec,
        "phase_duration_exclusions": [
            "turn 1 discard: phase_change recorded during intro "
            "(contains 3.75 s intro, not the 0.8 s bot-driven phase)"],
        "phase_duration_violations": dur_bad,
        "motion_states": states,
        "react_rows_sample": react_rows[:16],
        "react_row_count": len(react_rows),
        "homologous_framewise_ab": {
            "frame_source": "cap9 live run (same card/frame for both caps)",
            "sample_count": len(rows9),
            "jump_stats": jumps,
            "threshold_policy": ("首次量化，无历史外部锚；只报告分布，"
                                 "不做放行线，结论结合看图给出。"),
        },
        "capture_channel": {"live_frames": live_shas,
                            "sv_frames": sv_groups},
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("REPRODUCIBILITY",
          reproducibility["runs_compared"], "runs /",
          reproducibility["distinct_match_outcomes"],
          "distinct outcomes / seed_reproducible",
          reproducibility["seed_makes_match_reproducible"])
    print("PHASE_DURATIONS", dur)
    print("PHASE_VIOLATIONS", dur_bad)
    print("MOTION_STATES", states, "react_rows", len(react_rows))
    for side in ("player", "foe"):
        for cap in ("cap3", "cap9"):
            j = jumps[side][cap]
            print("JUMP", side, cap,
                  "peak_mean", j["peak_mean_deg"],
                  "peak_max", j["peak_max_deg"],
                  "intra_max", j["intra_max_deg"],
                  "intra_p95", j["intra_p95_deg"],
                  "boundary_max", j["boundary_max_deg"],
                  "zero_events", j["return_to_stance_events"],
                  "max_before_zero", j["max_leg_peak_before_zero_deg"])
    print("CAPTURE", live_shas, sv_groups)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LIVE_ANALYSIS_OK" if report["ok"]
          else "LIVE_ANALYSIS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
