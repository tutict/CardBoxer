"""P4 · 实机验收 · 汇总承重判据（只读盘，不重跑 Godot / Blender）。

纪律：
  * 上游报告的 ok 字段一律不信，独立复核 all(checks.values()) 与 failed；
  * 「实机」的定义本身要有源码判据：探针不冻结、不注入、不覆盖 mapping，
    且等渲染帧完成；只扫可执行行，注释满足不算（B 路线的教训）；
  * 跨进程逐帧像素 A/B 前提不成立，必须显式记录而不是偷偷硬比；
  * 连续帧跳变无历史外部锚，不设放行线；唯一数值上界 D_static 由
    两版表全量 284 帧独立复算得到。

用法：python verify_live_p4.py
产出：data/verify_live_p4.json
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
GAME = HERE.parent.parent / "CardBoxer"
P4 = HERE.parent / "native-plateau-p4"
LOGS = HERE / "logs"
PHASE_ORDER = ("discard", "select", "reveal", "resolve")


def load(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha(p: Path) -> str:
    return sha_bytes(Path(p).read_bytes())


def report_ok(rep: dict) -> bool:
    ck = rep.get("checks")
    if not isinstance(ck, dict) or not ck:
        return False
    if not all(v is True for v in ck.values()):
        return False
    if rep.get("failed"):
        return False
    return rep.get("ok", True) is True


def code_lines(src: str) -> list[str]:
    """只保留可执行行：注释里的裸子串会造成真空通过。"""
    return [ln for ln in src.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def main() -> int:
    live = load(D / "live_p4.json")
    ana = load(D / "live_p4_analysis.json")
    boards = load(D / "boards_p4.json")
    allc = load(D / "all_checks_live_p4.json")
    shabase = load(D / "sha_baseline.json")
    cases = live["cases"]
    payload = {tag: cases[tag]["payload"] for tag in cases}

    probe_path = HERE / "tests" / "p4_live_probe.gd"
    probe_src = probe_path.read_text(encoding="utf-8")
    code = "\n".join(code_lines(probe_src))
    deployed = GAME / "tests" / "p4_live_probe.gd"

    checks: dict[str, bool] = {}

    # ── 上游报告独立复核 ──
    checks["upstream_live_all_green"] = report_ok(live)
    checks["upstream_analysis_all_green"] = report_ok(ana)
    checks["upstream_boards_all_green"] = report_ok(boards)
    checks["upstream_three_reports_have_no_failed"] = all(
        not r.get("failed") for r in (live, ana, boards))
    checks["all_checks_15_of_15_green"] = (
        allc.get("total") == 15
        and allc.get("result") == "ALL GREEN"
        and not allc.get("failed")
        and isinstance(allc.get("checks"), list)
        and len(allc["checks"]) == 15
        and all(r.get("ok") is True and r.get("rc") == 0
                for r in allc["checks"]))
    pose = next((r for r in allc.get("checks", [])
                 if r.get("name") == "pose_probe"), {})
    checks["all_checks_pose_probe_pass"] = "PASS" in str(
        pose.get("summary", ""))

    # ── 「实机」的定义本身（源码形状，只扫可执行行）──
    checks["probe_code_never_freezes_arena"] = not re.search(
        r"arena\.paused\s*=\s*true", code, re.IGNORECASE)
    checks["probe_code_never_injects_apply"] = ".apply(" not in code
    checks["probe_code_never_overrides_mapping"] = not re.search(
        r"leg_cap_deg\"\]\s*=", code)
    checks["probe_code_waits_frame_post_draw"] = (
        "await RenderingServer.frame_post_draw" in code)
    checks["probe_code_reads_paused_and_delta"] = (
        "bool(arena.paused)" in code and "last_delta_deg" in code)
    checks["probe_copy_matches_game_deployed"] = (
        deployed.is_file() and sha(deployed) == sha(probe_path))
    checks["probe_not_in_watched_files"] = (
        "tests/p4_live_probe.gd" not in shabase["before"])

    # ── 两次真跑的采集健全性（从 payload 直接算）──
    checks["two_processes_both_rc0"] = all(
        cases[tag]["rc"] == 0 for tag in cases) and len(cases) == 2
    raw_logs = {}
    for tag in cases:
        p = LOGS / f"godot_p4_live_{tag}.log"
        t = p.read_text(encoding="utf-8") if p.is_file() else ""
        raw_logs[tag] = {
            "script_errors": t.count("SCRIPT ERROR")
            + t.count("Parse Error"),
            "marker_present": "P4_LIVE_JSON " in t,
            "bytes": len(t.encode("utf-8", "replace")),
        }
    checks["both_no_script_errors_raw_logs"] = all(
        v["script_errors"] == 0 and v["marker_present"]
        and v["bytes"] > 100 for v in raw_logs.values())
    checks["both_bot_true"] = all(
        payload[t].get("tk_bot") is True for t in cases)
    checks["both_three_turns"] = all(
        set(live["phase_sequences"][t].keys()) == {"1", "2", "3"}
        for t in cases)
    checks["both_phase_order_per_turn"] = all(
        tuple(v) == PHASE_ORDER
        for t in cases for v in live["phase_sequences"][t].values())
    checks["both_paused_never_true"] = all(
        payload[t].get("paused_violations") == 0
        and all(r.get("paused_live") is False
                for r in payload[t]["rows"]) for t in cases)
    checks["both_round_over_not_timeout"] = all(
        payload[t].get("end_reason") == "round_over" for t in cases)
    checks["both_final_phase_over"] = all(
        payload[t].get("final_round_phase") in ("over", "match_over")
        for t in cases)
    checks["use_3d_matches_tag"] = (
        payload["three_d"].get("use_3d") is True
        and payload["default_off"].get("use_3d") is False)
    checks["both_seed_matches"] = all(
        payload[t].get("seed") == live["seed"] for t in cases)
    checks["both_rows_above_50"] = all(
        len(payload[t]["rows"]) >= 50 for t in cases)
    checks["analysis_sample_count_equals_live_rows"] = (
        ana["sample_count"] == len(payload["three_d"]["rows"]))
    checks["sample_interval_0_12"] = live["sample_s"] == 0.12
    checks["three_d_cap_atan12_all_rows"] = all(
        r.get("cap_live") == "12.0000" and r.get("mode_live") == "atan"
        for r in payload["three_d"]["rows"])
    checks["three_d_15_cards_both"] = (
        payload["three_d"].get("cards_player") == 15
        and payload["three_d"].get("cards_foe") == 15)
    checks["three_d_frames_applied_growing"] = all(
        b["player"]["frames_applied"] > a["player"]["frames_applied"]
        for a, b in zip(payload["three_d"]["rows"],
                        payload["three_d"]["rows"][1:]))

    # ── P4 落生态确实被引擎读到 ──
    tm = live["table_markers"]
    checks["marker_2d_shipped_both"] = all(
        payload[t].get("marker_2d") == tm["want_2d_shipped"]
        for t in cases)
    checks["marker_2d_differs_from_p3"] = (
        tm["want_2d_shipped"] != tm["p3_2d"])
    checks["marker_3d_shipped_both"] = (
        payload["three_d"].get("marker_3d_player") == tm["want_3d_player"]
        and payload["three_d"].get("marker_3d_foe") == tm["want_3d_foe"])
    checks["marker_3d_differs_from_p3"] = (
        tm["want_3d_player"] != tm["p3_3d_player"]
        and tm["want_3d_foe"] != tm["p3_3d_foe"])
    checks["marker_rows_all_match_shipped"] = (
        not live["marker_mismatches"] and not ana["out_of_range_frames"])
    checks["engine_delta_matches_shipped"] = (
        not live["delta_mismatches"]
        and not ana["engine_delta_mismatches"])
    checks["no_monitored_game_file_modified"] = all(
        live["sha_unchanged"].values()) and len(live["sha_unchanged"]) >= 14
    checks["sha_baseline_matches_runner"] = (
        shabase["game"] == str(GAME)
        and shabase["before"] == live["sha_before"])

    # ── PNG 与看图产物 ──
    checks["live_pngs_all_nonzero_both"] = all(
        v["total"] > 0 and v["total"] == v["nonempty"]
        for v in live["png_stats"]["live"].values())
    checks["live_pngs_all_unique_both"] = all(
        v["total"] > 0 and v["total"] == v["unique_sha"]
        for v in live["png_stats"]["live"].values())
    checks["sv_pngs_all_nonzero"] = (
        live["png_stats"]["player_sv"]["three_d"]["total"] > 0
        and live["png_stats"]["player_sv"]["three_d"]["nonempty"]
        == live["png_stats"]["player_sv"]["three_d"]["total"])
    bd = boards["boards"]
    checks["three_boards_valid_png_signature"] = all(
        Path(bd[k]["path"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        for k in bd)
    checks["three_boards_sha_match_report"] = all(
        sha(Path(bd[k]["path"])) == bd[k]["sha256"] for k in bd)
    checks["three_boards_nonempty"] = all(
        Path(bd[k]["path"]).stat().st_size > 10000 for k in bd)
    checks["keyframes_from_both_tags"] = all(
        len(v) == 3 for v in bd["keyframes"]["picked"].values())
    checks["keyframes_cover_reveal_and_resolve"] = all(
        "reveal" in v and "resolve" in v
        for v in bd["keyframes"]["phases"].values())
    checks["strip_six_continuous_frames"] = (
        len(bd["strip"]["picked_idx"]) == 6
        and all(bd["strip"]["picked_idx"][i + 1]
                == bd["strip"]["picked_idx"][i] + 1 for i in range(5)))
    checks["timeline_zoom_single_continuous_segment"] = (
        len(bd["timeline"]["focus_zoom_frames"]) >= 2
        and all(bd["timeline"]["focus_zoom_frames"][i + 1]
                > bd["timeline"]["focus_zoom_frames"][i]
                for i in range(
                    len(bd["timeline"]["focus_zoom_frames"]) - 1)))
    checks["timeline_numbers_match_analysis"] = all(
        ana["jump_stats"][s]["p3"]["exact_flat_pairs"]
        == ana["jump_stats"][s]["p4"]["exact_flat_pairs"] + 9
        for s in ("player", "foe"))

    # ── 同源双表复算 ──
    checks["static_bound_recomputed_284_frames"] = (
        ana["static_bound"]["frames_compared"] == 284
        and ana["static_bound"]["max_abs_delta_diff_deg"] > 0)
    checks["live_delta_diff_within_static_bound"] = (
        ana["live_max_abs_delta_diff_deg"]
        <= ana["static_bound"]["max_abs_delta_diff_deg"] + 1e-6)
    checks["exact_flat_not_worse_both_sides"] = all(
        ana["jump_stats"][s]["p4"]["exact_flat_pairs"]
        <= ana["jump_stats"][s]["p3"]["exact_flat_pairs"]
        for s in ("player", "foe"))
    checks["max_jump_not_increased_both_sides"] = all(
        ana["jump_stats"][s]["p4"]["max_jump_deg"]
        <= ana["jump_stats"][s]["p3"]["max_jump_deg"] + 1e-6
        for s in ("player", "foe"))
    checks["extra_jump_distribution_recorded"] = all(
        ana["homologous_extra"][s]["pairs"] == ana["sample_count"] - 1
        and ana["homologous_extra"][s]["worst_extra_pair"] is not None
        for s in ("player", "foe"))
    checks["curves_cover_all_rows_both_tables"] = all(
        len(ana["curves"][s][w]) == ana["sample_count"]
        for s in ("player", "foe") for w in ("p3", "p4"))
    checks["stance_delta_zero_both_tables"] = (
        not ana["stance_violations"])
    checks["sv_duplicates_explained_by_delta"] = (
        not ana["capture_channel"]["sv"]["groups_with_mixed_delta"]
        and ana["capture_channel"]["sv"]["total"] > 0)
    checks["phase_durations_within_spec"] = (
        not ana["phase_duration_violations"])
    checks["framewise_pixel_ab_recorded_not_applicable"] = (
        live["preconditions"]["framewise_pixel_ab_applicable"] is False
        and "RNG" in live["preconditions"]["note"])
    checks["no_external_anchor_policy_recorded"] = (
        "不设放行线" in ana["threshold_policy"])
    checks["distinct_match_outcomes_recorded"] = (
        ana["distinct_match_outcomes"] >= 1
        and set(ana["match_outcomes"]) == set(cases))

    failed = [k for k, v in checks.items() if not v]
    report = {"checks": checks, "total": len(checks),
              "passed": len(checks) - len(failed),
              "failed": failed, "ok": not failed,
              "raw_logs": raw_logs}
    (D / "verify_live_p4.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("LIVE_P4_VERIFY %d/%d %s" % (
        report["passed"], report["total"],
        "ALL GREEN" if report["ok"] else "FAILED"))
    for k in failed:
        print("RED", k)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
