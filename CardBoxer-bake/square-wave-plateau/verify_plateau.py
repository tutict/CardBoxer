"""square-wave-plateau P3 · 汇总承重判据（只读盘，不重跑 Godot / Blender）。

纪律（逐条沿用 P2 / B 路线）：
  * 不信任何上游报告的 ok 字段，独立复核 checks 非空、全 True、failed 空；
  * 落盘真值直接从游戏工程重新读、与 pre-p3 备份递归逐值 diff；
  * 13 骨 delta、时间线曲线、推荐档、平台成因都用本区 p3_math 独立重算，
    不只看汇总数字；
  * PNG 除大小外还验签名与 IEND（只查大小会被改坏文件头绕过）；
  * 历史守卫债单独点名列边界，不折进 P3 判据计数。

用法：python verify_plateau.py
产出：data/verify_plateau.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
D = HERE / "data"
BOARDS = HERE / "boards"
ORIG = HERE / "orig" / "pre-p3"
OUT = D / "verify_plateau.json"
sys.path.insert(0, str(HERE))
from p3_math import LEG_BONES, expected_delta  # noqa: E402

P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5
EXPECTED_MODE, EXPECTED_CAP = "atan", 12.0
ARM_GAINS = {"f_upper": 32.0, "f_fore": 26.0,
             "b_upper": 28.0, "b_fore": 22.0}
TO_CHANGE = ("scripts/rig_driver.gd", "data/motion_input.json",
             "data/motion_input_foe.json")
BOARDS_EXPECTED = (
    "P3-timeline-square-wave.png",
    "P3-frame-sequence-strip.png",
    "P3-before-after-comparison.png",
    "P3-full-284-frames-tearing-tradeoff.png",
)
MODE_MATH = {"shipped": ("atan", 12.0), "rolled_back": ("hard", 9.0),
             "reapplied": ("atan", 12.0),
             "legacy_compat": ("hard", 9.0)}
MODE_LIVE = {"shipped": ("atan", 12.0), "rolled_back": ("hard", 9.0),
             "reapplied": ("atan", 12.0),
             "legacy_compat": ("<absent>", 9.0)}
# 实测得来的历史守卫红因：点名具体条目 + 同时断言集合与总数，
# 防「守卫被悄悄改宽」也防「红因扩散到新行为」。
EXPECTED_HISTORY_REDS = {
    "motion_p1": {"ten_untouched_unchanged",
                  "non_cards_fields_equal_backup_both",
                  "mapping_gains_unchanged_both"},
    "motion_p2": {"player_cap_is_9", "foe_cap_is_9",
                  "only_one_diff_path_player",
                  "only_one_diff_path_foe",
                  "other_12_watched_files_unchanged",
                  "three_core_scripts_sha_unchanged"},
    "live_match": {"shipped_cap_still_9_both"},
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jload(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def diff_paths(a, b, prefix: str = "") -> list[str]:
    if type(a) is not type(b):
        return [prefix or "<root>"]
    if isinstance(a, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            p = f"{prefix}.{k}" if prefix else k
            if k not in a or k not in b:
                out.append(p)
            else:
                out.extend(diff_paths(a[k], b[k], p))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [prefix or "<root>"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(diff_paths(x, y, f"{prefix}[{i}]"))
        return out
    return [] if a == b else [prefix or "<root>"]


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
    b = Path(p).read_bytes()
    return (len(b) > 1000 and b[:8] == b"\x89PNG\r\n\x1a\n"
            and b[-8:-4] == b"IEND")


def leg_peak(card: str, frame: int, mode: str, cap: float) -> float:
    d = expected_delta(card, frame, mode, cap)
    return round(max(abs(d[b]) for b in LEG_BONES), 2) if d else 0.0


def flat_pairs(series: list[float]) -> int:
    return sum(abs(b - a) < 1e-6
               for a, b in zip(series, series[1:]))


def main() -> int:
    mi = jload(GAME / "data" / "motion_input.json")
    mif = jload(GAME / "data" / "motion_input_foe.json")
    mi_bak = jload(ORIG / "motion_input.json")
    mif_bak = jload(ORIG / "motion_input_foe.json")
    rig_src = (GAME / "scripts" / "rig_driver.gd").read_text(
        encoding="utf-8")
    baseline = jload(D / "baseline_p3.json")
    apply_rep = jload(D / "apply_p3.json")
    diag = jload(D / "plateau_diagnosis.json")
    plan = jload(D / "plateau_plan.json")
    tear = jload(D / "plateau_tear.json")
    tear_bl = jload(D / "full_tear_blender.json")
    probe = jload(D / "p3_probe.json")
    boards = jload(D / "p3_boards.json")
    all_checks = jload(D / "all_checks_p3.json")
    gates = jload(D / "history_gates_p3.json")
    live = jload(BAKE / "live-match" / "data" / "live_match.json")

    checks: dict[str, bool] = {}
    errs: dict[str, str] = {}

    def add(name: str, fn) -> None:
        try:
            checks[name] = bool(fn())
        except Exception as exc:  # 守卫崩栈不算绿
            checks[name] = False
            errs[name] = repr(exc)

    # ── A 落盘真值：直接读游戏工程，不信任何报告 ──────────────
    add("player_mapping_atan_12", lambda: (
        mi["mapping"]["leg_mode"] == EXPECTED_MODE
        and mi["mapping"]["leg_cap_deg"] == EXPECTED_CAP))
    add("foe_mapping_atan_12", lambda: (
        mif["mapping"]["leg_mode"] == EXPECTED_MODE
        and mif["mapping"]["leg_cap_deg"] == EXPECTED_CAP))
    add("two_mappings_identical", lambda: mi["mapping"] == mif["mapping"])
    add("two_card_tables_identical", lambda: mi["cards"] == mif["cards"])
    add("cards_15_frames_284_both", lambda: all(
        len(m["cards"]) == 15
        and sum(int(c["frames"]) for c in m["cards"].values()) == 284
        for m in (mi, mif)))
    add("arm_gains_untouched_both", lambda: all(
        m["mapping"]["arm_gain_deg"] == ARM_GAINS for m in (mi, mif)))
    add("torso_caps_untouched_both", lambda: all(
        m["mapping"]["torso_cap_deg"] == 8.0 for m in (mi, mif)))
    add("only_two_diff_paths_player", lambda: diff_paths(mi_bak, mi)
        == ["mapping.leg_cap_deg", "mapping.leg_mode"])
    add("only_two_diff_paths_foe", lambda: diff_paths(mif_bak, mif)
        == ["mapping.leg_cap_deg", "mapping.leg_mode"])
    add("orig_backups_match_baseline_sha", lambda: all(
        sha(ORIG / Path(rel).name)
        == baseline["files"][rel]["sha256"] for rel in TO_CHANGE))
    add("other_11_watched_files_unchanged", lambda: all(
        (GAME / rel).is_file()
        and sha(GAME / rel) == meta["sha256"]
        for rel, meta in baseline["files"].items()
        if rel not in TO_CHANGE))
    add("rig_driver_helper_signature", lambda: (
        "func _leg(x: float, cap: float, mode: String) -> float:" in rig_src))
    add("atan_formula_constant_pinned", lambda: (
        "cap * (2.0 / PI) * atan((PI / 2.0) * x / cap)" in rig_src))
    add("legacy_fallback_clampf_present", lambda: (
        "return clampf(x, -cap, cap)" in rig_src))
    add("legacy_default_is_hard", lambda: (
        'mapping.get("leg_mode", "hard")' in rig_src))
    add("all_four_leg_bones_use_helper", lambda: all(
        f'"{b}": _leg(' in rig_src for b in LEG_BONES))
    add("no_inline_hard_clamp_left", lambda: (
        'clampf(float(raw["thigh_f"])' not in rig_src
        and 'clampf(float(raw["shin_b"])' not in rig_src))
    add("apply_report_three_single_replaces", lambda: (
        apply_rep["rows"]["scripts/rig_driver.gd"]
        ["bytewise_single_replace_each"] is True
        and all(apply_rep["rows"][rel]["bytewise_single_replace"] is True
                and apply_rep["rows"][rel]["diff_paths"]
                == ["mapping.leg_cap_deg", "mapping.leg_mode"]
                for rel in TO_CHANGE[1:])))
    add("apply_report_only_three_files_changed", lambda: all(
        apply_rep["untouched"].values())
        and len(apply_rep["untouched"]) == 11)
    add("baseline_report_all_checks_true", lambda: report_ok(baseline))
    add("apply_report_all_checks_true", lambda: report_ok(apply_rep))

    # ── B 上游报告自洽：独立复核 checks，不看 ok ────────────────
    add("diag_report_all_checks_true", lambda: report_ok(diag))
    add("tear_report_all_checks_true", lambda: report_ok(tear))
    add("probe_report_all_checks_true", lambda: report_ok(probe))
    add("boards_report_all_checks_true", lambda: report_ok(boards))
    add("history_gates_report_all_checks_true", lambda: report_ok(gates))
    add("all_checks_p3_15_15", lambda: (
        all_checks["total"] == 15 and all_checks["failed"] == []
        and all_checks["result"] == "ALL GREEN"
        and len(all_checks["checks"]) == 15
        and all(r["ok"] is True for r in all_checks["checks"])))

    # ── C 方波成因：独立重算，不只看汇总数字 ────────────────────
    q1, maps = diag["q1_cause"], diag["mappings"]
    add("cause_split_sums_to_total", lambda: (
        q1["exact_flat_from_native_track"]
        + q1["exact_flat_from_clamp"] == q1["exact_flat_pairs"]))
    add("hard09_platform_count_matches_tear", lambda: (
        q1["exact_flat_pairs"]
        == tear["per_case"]["hard09_baseline"]["exact_flat_pairs"]))
    add("atan12_removes_every_mapping_platform", lambda: (
        maps["atan12"]["exact_flat_from_mapping"] == 0
        and maps["atan12"]["exact_flat_pairs"]
        == maps["atan12"]["exact_flat_from_native_track"]))
    add("atan12_exact_flat_is_native_floor", lambda: (
        maps["atan12"]["exact_flat_pairs"] == tear["native_platform_floor"]
        == 255))
    add("atan12_perceptual_flat_below_hard09", lambda: (
        maps["atan12"]["perceptual_flat_pairs"]
        < maps["hard09"]["perceptual_flat_pairs"]))
    add("atan12_longest_run_shorter_than_hard09", lambda: (
        maps["atan12"]["longest_exact_flat_run_frames"]
        < maps["hard09"]["longest_exact_flat_run_frames"]))
    add("atan_beats_tanh_on_perceptual_flatness", lambda: (
        maps["atan12"]["perceptual_flat_pairs"]
        < maps["tanh12"]["perceptual_flat_pairs"]))
    add("contextual_norm_cannot_beat_stateless", lambda: (
        maps["norm09_track_peak"]["exact_flat_pairs"]
        >= maps["atan12"]["exact_flat_pairs"]
        and maps["norm09_track_peak"]["perceptual_flat_pairs"]
        > maps["atan12"]["perceptual_flat_pairs"]))
    add("live_action_plateau_reduced", lambda: (
        diag["live_match_curves"]["atan12"]["action_exact_flat_pairs"]
        < diag["live_match_curves"]["hard09"]["action_exact_flat_pairs"]))
    add("live_distinct_values_increased", lambda: (
        diag["live_match_curves"]["atan12"]["distinct_values"]
        > diag["live_match_curves"]["hard09"]["distinct_values"]))

    # ── D 全量真实 GLB 撕裂与推荐档 ────────────────────────────
    per = tear["per_case"]
    add("anchor_pinned_at_0_09365", lambda: (
        tear["anchor_p999_m"] == P999_LIMIT_M))
    add("plan_5_cases_284_frames_1420_poses", lambda: (
        len(plan["cases"]) == 5 and plan["frame_count"] == 284
        and len(plan["poses"]) == 1420 and len(plan["frames"]) == 284))
    add("full_1420_poses_evaluated", lambda: (
        tear_bl["poses_evaluated"] == 1420
        and len(tear_bl["rows"]) == 1420
        and tear_bl["poses_total_in_plan"] == 1420))
    add("real_glb_mesh_shape", lambda: (
        tear_bl["vertices"] == 57934 and tear_bl["edges"] == 136092
        and tear_bl["armature_bones"] == 14
        and tear_bl["chain_bones"] == 13
        and tear_bl["missing_bones"] == []))
    add("full_pose_matrix_err_within_limit", lambda: (
        tear_bl["max_pose_matrix_err"] < POSE_ERR_LIMIT))
    add("every_case_284_frames", lambda: all(
        v["frames"] == 284 for v in per.values()) and len(per) == 5)
    add("all_candidates_no_frame_over_anchor", lambda: all(
        v["frames_over_anchor"] == 0 for v in per.values()))
    add("all_candidates_within_anchor", lambda: all(
        v["worst_p999_m"] <= P999_LIMIT_M for v in per.values()))
    add("representative_sampling_gap_all_zero", lambda: all(
        abs(v) < 1e-9 for v in tear["sampling_gap_m"].values()))
    add("atan12_worst_p999_below_hard09_baseline", lambda: (
        per["atan12"]["worst_p999_m"]
        < per["hard09_baseline"]["worst_p999_m"]))
    add("atan12_leg_peak_mean_closest_to_baseline", lambda: (
        min((abs(v["leg_peak_mean_deg"]
                 - per["hard09_baseline"]["leg_peak_mean_deg"]), k)
            for k, v in per.items() if k != "hard09_baseline")[1]
        == "atan12"))
    add("all_soft_cases_at_platform_floor", lambda: all(
        per[k]["exact_flat_pairs"] == tear["native_platform_floor"]
        for k in ("atan09", "atan12", "atan15", "tanh12")))
    add("recommendation_rule_recomputed_is_atan12", lambda: (
        min((abs(v["leg_peak_mean_deg"]
                 - per["hard09_baseline"]["leg_peak_mean_deg"]), k)
            for k, v in per.items()
            if v["exact_flat_pairs"] == tear["native_platform_floor"]
            and v["worst_p999_m"] <= P999_LIMIT_M)[1]
        == tear["recommended_case"] == "atan12"))
    add("recommended_matches_shipped_mapping", lambda: (
        tear["recommended_case"] == "atan12"
        and per["atan12"]["leg_peak_max_deg"] <= EXPECTED_CAP))

    # ── E 引擎内上线态：13 骨 delta 独立复算 ────────────────────
    payload, rows = probe["main"]["payload"], probe["rows"]
    by_key = {r["key"]: r for r in rows}
    diffs = probe["diff_px"]
    add("shipped_readback_atan_12_both_sides", lambda: (
        payload.get("mapping_mode_player") == "atan"
        and payload.get("mapping_mode_foe") == "atan"
        and payload.get("mapping_cap_player") == 12.0
        and payload.get("mapping_cap_foe") == 12.0))
    add("use_3d_and_15_cards", lambda: (
        payload.get("use_3d") is True and payload.get("cards_player") == 15
        and payload.get("cards_foe") == 15))
    add("48_rows_four_modes_twelve_frames", lambda: (
        len(rows) == 48 and len(probe["modes"]) == 4
        and len(probe["frames"]) == 12))
    add("mode_readback_matches_every_scene", lambda: all(
        r.get(f"mode_live_{side}") == MODE_LIVE[r["mode"]][0]
        and abs(float(r.get(f"cap_live_{side}", -1))
                - MODE_LIVE[r["mode"]][1]) < 1e-6
        for r in rows for side in ("player", "foe")))
    add("delta_13_bones_independently_recomputed", lambda: all(
        (lambda exp, got: bool(exp) and bool(got) and all(
            abs(float(got.get(k, 1e9)) - exp[k]) < 1e-3 for k in exp))(
                expected_delta(r["card"], r["frame"],
                               *MODE_MATH[r["mode"]]),
                r.get(f"{side}_delta", {}))
        for r in rows for side in ("player", "foe")))
    add("no_leg_bone_over_cap_in_any_row", lambda: all(
        max(abs(float(r[f"{side}_delta"][b])) for b in LEG_BONES)
        <= MODE_MATH[r["mode"]][1] + 0.05
        for r in rows for side in ("player", "foe")))
    action = [k for k in diffs
              if k.startswith("shipped_vs_rolled_back")
              and "stance" not in k]
    stance = [k for k in diffs
              if k.startswith("shipped_vs_rolled_back")
              and "stance" in k]
    reapp = [k for k in diffs if k.startswith("shipped_vs_reapplied")]
    legacy = [k for k in diffs if k.startswith("shipped_vs_legacy_compat")]
    add("every_action_frame_changed_both_sides", lambda: (
        len(action) == 2 * (len(probe["frames"]) - 1)
        and all(diffs[k] > 0 for k in action)))
    add("stance_untouched_pixel_zero", lambda: (
        len(stance) == 2 and all(diffs[k] == 0 for k in stance)))
    add("shipped_reapplied_identical_same_process", lambda: (
        len(reapp) == 2 * len(probe["frames"])
        and all(diffs[k] == 0 for k in reapp)))
    add("legacy_compat_equals_rollback", lambda: (
        len(legacy) == len(action) + len(stance)
        and all(diffs[k] == diffs[k.replace(
            "legacy_compat", "rolled_back")] for k in legacy)))
    add("hp_unchanged_and_no_scenario_errors", lambda: (
        payload.get("hp") == [100, 100]
        and probe["main"]["scenario_errors"] == 0))
    add("no_script_errors_main_and_default", lambda: (
        probe["main"]["rc"] == 0 and probe["main"]["script_errors"] == 0
        and probe["default"]["rc"] == 0
        and probe["default"]["script_errors"] == 0))
    add("default_zero_pollution", lambda: all(
        probe["default"]["payload"].get(k) is False
        for k in ("use_3d", "layer_3d", "layer_3d_foe",
                  "player_override", "enemy_override"))
        and probe["default"]["payload"].get("env_3d") == "")
    add("all_96_sv_pngs_valid_signature", lambda: all(
        png_ok(Path(r[f"{side}_sv"])) for r in rows
        for side in ("player", "foe")))
    add("probe_script_bytewise_in_game", lambda: (
        (GAME / "tests" / "p3_plateau_probe.gd").is_file()
        and sha(GAME / "tests" / "p3_plateau_probe.gd")
        == sha(HERE / "tests" / "p3_plateau_probe.gd")))
    add("strip_32_source_panels_all_present", lambda: all(
        Path(by_key[f"{mode}-sweep{fr:02d}"][f"{side}_sv"]).is_file()
        for fr in range(14, 22)
        for mode, side in (("rolled_back", "player"),
                           ("shipped", "player"),
                           ("rolled_back", "foe"),
                           ("shipped", "foe"))))
    add("compare_six_source_panels_all_present", lambda: all(
        Path(by_key[f"{mode}-{card}{fr:02d}"]["player_sv"]).is_file()
        for card, fr in (("jab", 1), ("sweep", 7), ("hit_heavy", 1))
        for mode in ("rolled_back", "shipped")))

    # ── F 时间线与看图产物：曲线独立重算 ────────────────────────
    live_rows = live["cases"]["cap9"]["payload"]["rows"]
    series_h = [leg_peak(str(r["player"]["card"]),
                         int(r["player"]["frame"]), "hard", 9.0)
                for r in live_rows]
    series_a = [leg_peak(str(r["player"]["card"]),
                         int(r["player"]["frame"]), "atan", 12.0)
                for r in live_rows]
    tl = boards["made"]["timeline"]
    add("four_boards_present_and_sized", lambda: all(
        (BOARDS / n).is_file() and (BOARDS / n).stat().st_size > 30000
        for n in BOARDS_EXPECTED))
    add("four_boards_valid_png_signature", lambda: all(
        png_ok(BOARDS / n) for n in BOARDS_EXPECTED))
    add("timeline_129_real_samples", lambda: (
        len(live_rows) == tl["samples"] == 129))
    add("timeline_flat_stats_independently_recomputed", lambda: (
        flat_pairs(series_h) == tl["hard9_flat_pairs"]
        and flat_pairs(series_a) == tl["atan12_flat_pairs"]
        and len(set(series_h)) == tl["hard9_distinct"]
        and len(set(series_a)) == tl["atan12_distinct"]))
    add("timeline_plateau_reduced", lambda: (
        flat_pairs(series_a) < flat_pairs(series_h)))
    add("timeline_distinct_increased", lambda: (
        len(set(series_a)) > len(set(series_h))))
    add("timeline_peak_never_exceeds_atan_cap", lambda: (
        max(series_a) <= EXPECTED_CAP))
    add("strip_32_panels", lambda: boards["made"]["strip"]["panels"] == 32)
    add("compare_three_frames", lambda: (
        len(boards["made"]["compare"]["frames"]) == 3))

    # ── G 历史守卫债：实测名单点名 + 归档原字节还原证明 ──────────
    gate_rows = {r["tag"]: r for r in gates["rows"]}
    add("history_gates_three_reports_restored_bytewise", lambda: (
        len(gate_rows) == 3 and all(
            r.get("restored_sha_equal") is True
            for r in gate_rows.values())))
    add("history_reds_exactly_ten_expected_entries", lambda: (
        sum(len(gate_rows[t].get("failed", []))
            for t in EXPECTED_HISTORY_REDS) == 10
        and all(set(gate_rows[t].get("failed", [])) == names
                for t, names in EXPECTED_HISTORY_REDS.items())))
    add("history_reds_are_only_snapshot_or_old_value", lambda: all(
        any(word in f for word in (
            "unchanged", "equal_backup", "cap_is_9", "cap_still_9",
            "diff_path", "sha_", "gains"))
        for r in gate_rows.values() for f in r.get("failed", [])))

    report = {
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "errors": errs, "total": len(checks),
        "passed": sum(1 for v in checks.values() if v),
        "shipped_mapping": {"leg_mode": EXPECTED_MODE,
                            "leg_cap_deg": EXPECTED_CAP},
        "external_anchor_p999_m": P999_LIMIT_M,
        "native_platform_floor": tear["native_platform_floor"],
        "historical_reds": {t: sorted(n) for t, n in
                            EXPECTED_HISTORY_REDS.items()},
        "ok": all(checks.values()) and not errs,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    for k, v in errs.items():
        print("ERROR", k, v)
    print(f"PLATEAU_VERIFY {report['passed']}/{report['total']} "
          f"{'ALL GREEN' if report['ok'] else 'FAILED'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
