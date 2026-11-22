"""B 路线「实跑一局」· 汇总承重判据（只读盘，不重跑 Godot）。

纪律：
  * 不信任何上游报告的 ok 字段，独立复核 checks 非空、全 True、failed 空；
  * 落盘真值直接从游戏工程重新读 sha，与 P2 基线 / P2 上线后 sha 对账；
  * 真跑条件（不冻结、不注入动作、不推进游戏时钟）钉探针源码的**调用形态**，
    不钉裸标识符——注释里也会提到 paused / _tick_taikou；
  * 节奏、四态、截图唯一性、同源逐帧 A/B 的 jump 统计都从
    data/live_match.json 原始 rows 独立重算，不只信分析脚本的汇总；
  * 跨进程牌局 RNG 漂移导致「逐帧像素 A/B 前提不成立」是**点名的 N/A**，
    不折进判据计数、不硬比；
  * 连续帧跳变首次量化无外部锚，只作观察值记录，不做放行线。

用法：python verify_live.py
产出：data/verify_live.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_live as al  # noqa: E402
from run_live_match import PHASE_ORDER, phase_sequence  # noqa: E402

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
D = HERE / "data"
BOARDS = HERE / "boards"
LOGS = HERE / "logs"
OUT = D / "verify_live.json"

PNG_BOARDS = ("live-match-rhythm-timeline.png", "live-match-full-keyframes.png",
              "live-match-frame-sequence-review.png")
GIFS = ("live-match-player-motion.gif", "live-match-foe-motion.gif")
ADDED_JUMP_KEYS = {"peak_mean_deg", "peak_max_deg",
                   "intra_max_over_cap3", "peak_mean_over_cap3"}

# expected_delta 每次调用会重读两份动作表；给复算加缓存，公式本身不变。
_raw_expected = al.expected_delta
_cache: dict[tuple, dict] = {}


def cached_expected(card: str, frame: int, cap: float) -> dict:
    k = (card, frame, cap)
    if k not in _cache:
        _cache[k] = _raw_expected(card, frame, cap)
    return _cache[k]


al.expected_delta = cached_expected


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jload(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def report_ok(rep: dict) -> bool:
    ck = rep.get("checks")
    if not isinstance(ck, dict) or not ck:
        return False
    if not all(v is True for v in ck.values()):
        return False
    if rep.get("failed"):
        return False
    return rep.get("ok", True) is True


def png_ok(p: Path) -> bool:
    p = Path(p)
    if not p.is_file() or p.stat().st_size < 32:
        return False
    with p.open("rb") as f:
        head = f.read(8)
        f.seek(-12, 2)
        tail = f.read(12)
    return head == b"\x89PNG\r\n\x1a\n" and b"IEND" in tail


def gif_ok(p: Path) -> bool:
    p = Path(p)
    if not p.is_file() or p.stat().st_size <= 1000:
        return False
    with p.open("rb") as f:
        return f.read(6) in (b"GIF89a", b"GIF87a")


def code_lines(text: str) -> list[str]:
    """去掉注释行与空行，用于证明注释订正没动可执行行。"""
    return [ln.rstrip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def recomputed_jumps(rows: list) -> dict:
    curves = {}
    for side in ("player", "foe"):
        curves[side] = {"cap3": al.leg_series(rows, side, 3.0),
                        "cap9": al.leg_series(rows, side, 9.0)}
    jumps = {s: {c: al.jump_stats(curves[s][c])
                 for c in ("cap3", "cap9")} for s in curves}
    peaks = {}
    for s in curves:
        peaks[s] = {}
        for c in ("cap3", "cap9"):
            v = [p["leg_peak"] for p in curves[s][c]]
            peaks[s][c] = {
                "peak_mean_deg": round(sum(v) / len(v), 4),
                "peak_max_deg": max(v),
            }
    for s in curves:
        a, b = jumps[s]["cap3"], jumps[s]["cap9"]
        b["peak_mean_deg"] = peaks[s]["cap9"]["peak_mean_deg"]
        b["peak_max_deg"] = peaks[s]["cap9"]["peak_max_deg"]
        a["peak_mean_deg"] = peaks[s]["cap3"]["peak_mean_deg"]
        a["peak_max_deg"] = peaks[s]["cap3"]["peak_max_deg"]
        b["intra_max_over_cap3"] = round(
            b["intra_max_deg"] / a["intra_max_deg"], 4
        ) if a["intra_max_deg"] > 0 else None
        b["peak_mean_over_cap3"] = round(
            b["peak_mean_deg"] / a["peak_mean_deg"], 4
        ) if a["peak_mean_deg"] > 0 else None
    return jumps


def main() -> int:
    live = jload(D / "live_match.json")
    ana = jload(D / "live_analysis.json")
    boards = jload(D / "live_boards.json")
    strip = jload(D / "transition_strip.json")
    checks_green = jload(D / "all_checks_live.json")
    baseline = jload(D / "baseline_live.json")
    cases = live["cases"]
    p9 = cases["cap9"]["payload"]
    p3 = cases["cap3"]["payload"]
    rows9, rows3 = p9["rows"], p3["rows"]
    src = (HERE / "tests" / "live_match_probe.gd").read_text(
        encoding="utf-8")
    evidence = (HERE / "orig" / "live_match_probe-evidence.gd").read_text(
        encoding="utf-8")
    first_log = (LOGS / "live_cap9.out").read_text(encoding="utf-8")

    # 独立重算：同源逐帧 A/B 的全部 jump 统计
    recomputed = recomputed_jumps(rows9)
    reported = ana["homologous_framewise_ab"]["jump_stats"]

    checks: dict[str, bool] = {}
    errs: dict[str, str] = {}

    def add(name: str, fn) -> None:
        try:
            checks[name] = bool(fn())
        except Exception as exc:  # 守卫崩栈不算绿
            checks[name] = False
            errs[name] = repr(exc)

    # ── A 落盘真值：B 路线零改动 ────────────────────────────────
    add("baseline_live_report_all_checks_true", lambda: report_ok(baseline))
    add("game_probe_matches_source_bytewise", lambda: sha(
        GAME / "tests" / "live_match_probe.gd")
        == sha(HERE / "tests" / "live_match_probe.gd"))
    add("evidence_probe_bytes_preserved_and_distinct", lambda: (
        (HERE / "orig" / "live_match_probe-evidence.gd").is_file()
        and sha(HERE / "orig" / "live_match_probe-evidence.gd")
        != sha(HERE / "tests" / "live_match_probe.gd")))
    add("comment_fix_changed_only_comment_lines", lambda:
        code_lines(evidence) == code_lines(src))
    add("shipped_cap_still_9_both", lambda: all(
        jload(GAME / rel)["mapping"]["leg_cap_deg"] == 9.0
        for rel in ("data/motion_input.json", "data/motion_input_foe.json")))

    # ── B 探针纪律：这是真跑，不是冻结/注入 ─────────────────────
    add("probe_never_pauses_arena", lambda: (
        "paused = true" not in src
        and not re.search(r"\.paused\s*=(?!=)", src)))
    add("probe_never_injects_apply", lambda: ".apply(" not in src)
    add("probe_never_advances_game_clock", lambda: (
        not re.search(r"arena\.(_tick_taikou|tk_phase_time|tk_rhythm_t)"
                      r"\s*=(?!=)", src)))
    # 必须扫「代码行」而不是全文裸子串：头部注释里也写着
    # 「截图必须 await RenderingServer.frame_post_draw」，全文子串会被
    # 注释满足，改坏代码行仍判绿（M06 变异实测出来的真空通过）。
    add("probe_reads_real_driver_state", lambda: all(
        any(k in ln for ln in code_lines(src))
        for k in ("last_delta_deg", "last_card", "frames_applied")))
    add("probe_waits_frame_post_draw", lambda: any(
        "await RenderingServer.frame_post_draw" in ln
        for ln in code_lines(src)))
    add("probe_comment_matches_code", lambda: (
        "截图必须 await RenderingServer.frame_post_draw" in src
        and "不 await frame_post_draw" not in src))
    add("cap9_uses_shipped_mapping_without_override", lambda: (
        p9["cap_override"] == -1.0
        and "LIVE_MATCH_CAP" not in cases["cap9"]["extra"]))
    add("cap3_override_only_via_env", lambda: (
        p3["cap_override"] == 3.0
        and cases["cap3"]["extra"].get("LIVE_MATCH_CAP") == "3.0"))

    # ── C 上游报告自洽：独立复核，不看 ok ───────────────────────
    add("live_match_report_all_checks_true", lambda: (
        report_ok(live) and len(live["checks"]) == 26))
    add("live_analysis_report_all_checks_true", lambda: (
        report_ok(ana) and len(ana["checks"]) == 7))
    add("live_boards_report_all_checks_true", lambda: report_ok(boards))
    add("transition_strip_report_all_checks_true", lambda: report_ok(strip))
    add("all_checks_live_15_15", lambda: (
        checks_green["total"] == 15
        and checks_green["failed"] == []
        and checks_green["result"] == "ALL GREEN"
        and len(checks_green["checks"]) == 15
        and all(r["ok"] is True and r["rc"] == 0
                for r in checks_green["checks"])))

    # ── D 真跑条件 ──────────────────────────────────────────────
    for tag, p in (("cap9", p9), ("cap3", p3)):
        c = cases[tag]
        add(f"{tag}_rc0_no_script_or_scenario_errors", lambda c=c: (
            c["rc"] == 0 and c["script_errors"] == 0
            and c["scenario_errors"] == 0))
        add(f"{tag}_round_over_not_timeout", lambda p=p:
            p["end_reason"] == "round_over"
            and p["final_round_phase"] in ("over", "match_over"))
        add(f"{tag}_3d_and_bot_and_env", lambda p=p, c=c: (
            p["use_3d"] is True and p["tk_bot"] is True
            and p["env_3d"] == "1" and p["env_bot"] == "1"
            and c["extra"].get("CARD_BOXER_3D") == "1"
            and c["extra"].get("CARD_BOXER_TAIKOU_BOT") == "1"))
        add(f"{tag}_cap_readback_matches_case", lambda p=p, c=c:
            p["cap_readback"] == c["cap"])
        add(f"{tag}_15_cards_both", lambda p=p: (
            p["cards_player"] == 15 and p["cards_foe"] == 15))
        add(f"{tag}_all_rows_cap_live", lambda p=p, c=c: all(
            r["cap_live"] == c["cap"] for r in p["rows"]))
        add(f"{tag}_frames_applied_strictly_growing", lambda p=p: all(
            b["player"]["frames_applied"] > a["player"]["frames_applied"]
            for a, b in zip(p["rows"], p["rows"][1:])))
    add("same_seed_both_runs", lambda: (
        live["seed"] == 20261114 and p9["seed"] == 20261114
        and p3["seed"] == 20261114))
    add("both_runs_same_row_count_and_sample_s", lambda: (
        len(rows9) == len(rows3) == 129
        and p9["sample_s"] == p3["sample_s"] == 0.12))
    add("all_rows_delta_match_python_formula", lambda:
        live["delta_mismatches"] == []
        and live["checks"]["all_rows_delta_match_python_formula"] is True)

    # ── E 节奏与四表现态（从原始 rows 独立重算） ────────────────
    add("three_turns_four_phases_each_recomputed", lambda: all(
        set(seq.keys()) == {"1", "2", "3"}
        and all(tuple(v) == PHASE_ORDER for v in seq.values())
        for seq in (phase_sequence(p9), phase_sequence(p3))))
    add("phase_sequences_match_report", lambda: (
        phase_sequence(p9) == live["phase_sequences"]["cap9"]
        and phase_sequence(p3) == live["phase_sequences"]["cap3"]))

    def four_states(rows: list) -> dict:
        return {
            "reveal_focus": any(r["tk_phase"] == "reveal"
                                and r["player"]["card"] == "focus"
                                and r["foe"]["card"] == "focus"
                                for r in rows),
            "winner_attack": any(r["tk_phase"] == "resolve" and (
                (r["player"]["card"] != "stance"
                 and not r["player"]["card"].startswith("hit_"))
                or (r["foe"]["card"] != "stance"
                    and not r["foe"]["card"].startswith("hit_")))
                for r in rows),
            "loser_react": any(r["tk_phase"] == "resolve" and (
                r["player"]["card"].startswith("hit_")
                or r["foe"]["card"].startswith("hit_")) for r in rows),
            "draw_both_react": any(
                r["tk_phase"] == "resolve" and r["tk_winner"] == "draw"
                and r["player"]["card"].startswith("hit_")
                and r["foe"]["card"].startswith("hit_") for r in rows),
        }

    add("four_motion_states_recomputed_from_rows", lambda: all(
        four_states(rows9).values()))
    add("four_motion_states_match_analysis", lambda:
        four_states(rows9) == ana["motion_states"])
    add("no_phase_duration_violations", lambda:
        ana["phase_duration_violations"] == [])
    add("phase_spec_pinned", lambda: (
        ana["phase_spec_s"] == {"discard": 0.8, "select": 0.8,
                                "reveal": 1.5, "resolve": 1.9}
        and ana["phase_tol_s"] == 0.25))
    add("hitstop_policy_consistent_per_turn", lambda: all(
        (v["hitstop_s"] == (0.0 if v["winner"] in ("", "draw")
                            else 0.24))
        and abs(v["resolve_spec_s"] - (1.9 + v["hitstop_s"])) < 1e-9
        for by_turn in ana["effective_phase_spec"].values()
        for v in by_turn.values()))
    add("turn1_discard_exclusion_recorded", lambda: any(
        "turn 1 discard" in s for s in
        ana["phase_duration_exclusions"]))
    add("react_rows_present_and_all_hit_tracks", lambda: (
        ana["react_row_count"] > 0
        and all(any(x.startswith("hit_") for x in r[2:])
                for r in ana["react_rows_sample"])))

    # ── F 截图通道健全性 ────────────────────────────────────────
    def live_paths(p: dict) -> list[Path]:
        return [Path(r["live"]) for r in p["rows"]
                if r.get("live") and Path(r["live"]).is_file()]

    def all_shot_paths(p: dict) -> list[Path]:
        out = []
        for r in p["rows"]:
            for k in ("live", "player_sv", "foe_sv"):
                v = r.get(k)
                if v and Path(v).is_file():
                    out.append(Path(v))
        return out

    for tag, p in (("cap9", p9), ("cap3", p3)):
        add(f"{tag}_24_live_frames_all_unique", lambda p=p: (
            len(live_paths(p)) == 24
            and len({sha(q) for q in live_paths(p)}) == 24))
        add(f"{tag}_all_shot_png_signatures_valid", lambda p=p: (
            len(all_shot_paths(p)) > 100
            and all(png_ok(q) for q in all_shot_paths(p))))
        add(f"{tag}_shots_file_count_matches_rows", lambda tag=tag, p=p: (
            len(list((HERE / "shots" / tag).glob("*.png")))
            == len(all_shot_paths(p))))

    def sv_groups_clean(tag: str, cap: float) -> bool:
        groups = defaultdict(list)
        for r in cases[tag]["payload"]["rows"]:
            v = r.get("player_sv")
            if v and Path(v).is_file():
                groups[sha(Path(v))].append(
                    (r["player"]["card"], r["player"]["frame"]))
        return (len(groups) > 0
                and all(len({al.delta_signature(c, f, cap)
                             for c, f in items}) == 1
                        for items in groups.values()))

    add("sv_duplicates_explained_by_retargeted_delta", lambda: (
        sv_groups_clean("cap9", 9.0) and sv_groups_clean("cap3", 3.0)))
    add("three_png_boards_valid_signature", lambda: all(
        png_ok(BOARDS / n) and (BOARDS / n).stat().st_size > 50000
        for n in PNG_BOARDS))
    add("two_gifs_valid_signature_and_88_frames", lambda: (
        all(gif_ok(BOARDS / n) for n in GIFS)
        and boards["made"]["player_gif"]["frames"] == 88
        and boards["made"]["foe_gif"]["frames"] == 88))
    add("keyframes_board_sources_all_present", lambda: (
        len(boards["made"]["keyframes"]["frames"]) == 8
        and all(Path(p).is_file()
                for p in boards["made"]["keyframes"]["frames"])))
    add("transition_strip_42_panels_three_groups", lambda: (
        strip["present_panels"] == strip["expected_panels"] == 42
        and len(strip["groups"]) == 3
        and all(len(g["idx"]) == 7 for g in strip["groups"])))

    # ── G 同源逐帧 A/B 与诚实边界 ───────────────────────────────
    add("homologous_frame_source_is_cap9_live_run", lambda:
        "cap9 live run" in
        ana["homologous_framewise_ab"]["frame_source"])
    add("four_jump_series_present", lambda: (
        set(reported.keys()) == {"player", "foe"}
        and all(set(v.keys()) == {"cap3", "cap9"}
                for v in reported.values())))
    add("jump_key_sets_match_recomputation", lambda: all(
        {k for k in reported[s][c] if k not in ADDED_JUMP_KEYS}
        == {k for k in recomputed[s][c] if k not in ADDED_JUMP_KEYS}
        for s in ("player", "foe") for c in ("cap3", "cap9")))
    add("jump_numeric_fields_match_recomputation", lambda: all(
        all(reported[s][c][k] == recomputed[s][c][k]
            for k in recomputed[s][c] if k not in ADDED_JUMP_KEYS)
        for s in ("player", "foe") for c in ("cap3", "cap9")))
    add("peak_stats_match_recomputation", lambda: all(
        all(abs(float(reported[s][c].get(k, float("nan")))
                - float(recomputed[s][c].get(k, float("nan")))) < 1e-6
            for k in ("peak_mean_deg", "peak_max_deg"))
        and all(abs(float(reported[s]["cap9"].get(k, float("nan")))
                    - float(recomputed[s]["cap9"].get(k, float("nan"))))
                < 1e-6
                for k in ("intra_max_over_cap3", "peak_mean_over_cap3"))
        for s in ("player", "foe") for c in ("cap3", "cap9")))
    add("cap3_peak_max_3_cap9_peak_max_9_both_sides", lambda: all(
        reported[s]["cap3"]["peak_max_deg"] == 3.0
        and reported[s]["cap9"]["peak_max_deg"] == 9.0
        for s in ("player", "foe")))
    add("cap9_peak_mean_about_triple_cap3", lambda: all(
        2.5 <= reported[s]["cap9"]["peak_mean_over_cap3"] <= 3.2
        for s in ("player", "foe")))
    add("cap9_intra_max_exceeds_cap3_both_sides", lambda: all(
        reported[s]["cap9"]["intra_max_deg"]
        > reported[s]["cap3"]["intra_max_deg"]
        for s in ("player", "foe")))
    add("zero_residual_recorded_and_larger_at_cap9", lambda: (
        reported["player"]["cap9"]["max_leg_peak_before_zero_deg"] > 5.0
        and reported["player"]["cap9"]["max_leg_peak_before_zero_deg"]
        > reported["player"]["cap3"]["max_leg_peak_before_zero_deg"]))
    add("jump_threshold_is_not_a_release_gate", lambda:
        "不做放行线" in ana["homologous_framewise_ab"]["threshold_policy"])
    add("reproducibility_na_pointed_not_folded_into_gate", lambda: (
        live["preconditions"]["framewise_ab_applicable"] is False
        and live["preconditions"]["fingerprint_equal"] is False
        and ana["reproducibility"]["framewise_pixel_ab_applicable"] is False
        and ana["reproducibility"]["seed_makes_match_reproducible"] is False
        and ana["reproducibility"]["runs_compared"] == 3
        and ana["reproducibility"]["distinct_match_outcomes"] == 3
        and "前提不成立" in ana["reproducibility"]["note"]))
    add("first_solo_run_fingerprint_logged", lambda:
        "FP cap9 " in first_log)
    add("framewise_pixel_ab_na_named_in_note", lambda:
        "逐帧像素 A/B" in ana["reproducibility"]["note"]
        and not ana["reproducibility"]["framewise_pixel_ab_applicable"])

    report = {
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "errors": errs,
        "total": len(checks),
        "passed": sum(1 for v in checks.values() if v),
        "seed": live["seed"],
        "rows_per_run": len(rows9),
        "ok": all(checks.values()) and not errs,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    for k, v in errs.items():
        print("ERROR", k, v)
    print(f"LIVE_VERIFY {report['passed']}/{report['total']} "
          f"{'ALL GREEN' if report['ok'] else 'FAILED'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
