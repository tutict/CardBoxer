"""原生平台 P4 · 汇总承重判据（只读盘，不重跑 Godot / Blender）。

纪律（逐条沿用 P2 / B / P3）：
  * 不信任何上游报告的 ok 字段，独立复核 checks 非空、全 True、failed 空；
  * 落盘真值直接从游戏工程重新读，与 orig/pre-p4 备份递归逐值 diff；
  * 13 骨 delta 用本区 p4_math 独立重算，与引擎探针逐行逐骨对账；
  * PNG 除大小外还验签名与 IEND；
  * 历史守卫债用 before/after 实测对账，点名新增红因，不折进判据计数；
  * 任意判据抛异常记 errors 并算红，不静默跳过。

用法：python verify_native.py
产出：data/verify_native.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
D = HERE / "data"
BOARDS = HERE / "boards"
ORIG = HERE / "orig" / "pre-p4"
OUT = D / "verify_native.json"
sys.path.insert(0, str(HERE))
from p4_math import LEG_BONES, expected_delta, tracks  # noqa: E402

P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5
EXPECTED_MODE, EXPECTED_CAP = "atan", 12.0
LEG_JOINTS = ("f_knee", "f_foot", "b_knee", "b_foot")
TO_CHANGE = ("data/card_motion.json", "data/motion_input.json",
             "data/motion_input_foe.json")
BOARDS_EXPECTED = (
    "P4-candidate-tradeoffs.png", "P4-full-tearing-tradeoff.png",
    "P4-plateau-curve-comparison.png", "P4-frame-sequence-strip.png", "P4-before-after-comparison.png",
)
# 落地前绿、落地后新增红的历史守卫条目（实测，见 history_gates_p4_*.json）
EXPECTED_NEW_REDS = {
    "motion_p1": {"original_three_unchanged_both"},
    "motion_p2": set(),
    "live_match": {"jump_numeric_fields_match_recomputation",
                   "peak_stats_match_recomputation"},
    "plateau_p3": {"delta_13_bones_independently_recomputed",
                   "only_two_diff_paths_foe",
                   "only_two_diff_paths_player",
                   "other_11_watched_files_unchanged",
                   "timeline_flat_stats_independently_recomputed"},
}


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


def diff_paths(a, b, prefix: str = "") -> list[str]:
    if type(a) is not type(b):
        return [prefix or "<root>"]
    if isinstance(a, dict):
        out = []
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


def all_tracks(obj: dict) -> dict:
    out = {k: v["track"] for k, v in obj["cards"].items()}
    out.update({k: v["track"] for k, v in obj.get("motions", {}).items()})
    return out


def png_ok(p: Path, min_size: int = 20000) -> bool:
    if not p.is_file() or p.stat().st_size < min_size:
        return False
    b = p.read_bytes()
    return (b[:8] == b"\x89PNG\r\n\x1a\n"
            and b[-12:-8] == b"\x00\x00\x00\x00"
            and b[-8:-4] == b"IEND")


def main() -> int:
    reports = {
        k: jload(D / f)
        for k, f in {
            "diag": "native_diagnosis.json",
            "scan": "candidate_scan.json",
            "tear": "native_tear.json",
            "layout": "layout_probe.json",
            "landing": "landing_tracks.json",
            "decision": "landing_decision.json",
            "micro2_tear": "micro2_tear.json",
            "baseline": "baseline_p4.json",
            "apply": "apply_native.json",
            "readback": "readback_native.json",
            "probe": "p4_probe.json",
            "boards": "p4_boards.json",
            "all_checks": "all_checks_p4.json",
            "gates_before": "history_gates_p4_before.json",
            "gates_after": "history_gates_p4_after.json",
        }.items()
    }
    cm = jload(GAME / "data" / "card_motion.json")
    mi = jload(GAME / "data" / "motion_input.json")
    mif = jload(GAME / "data" / "motion_input_foe.json")
    cm0 = jload(ORIG / "card_motion.json")
    mi0 = jload(ORIG / "motion_input.json")
    mif0 = jload(ORIG / "motion_input_foe.json")
    keys = list(mi["joint_names"])
    landing = reports["landing"]
    probe = reports["probe"]
    apply_rep = reports["apply"]

    def joints_map(obj):
        return {card: [{k: tuple(float(x) for x in f[k]) for k in keys}
                       for f in tr]
                for card, tr in all_tracks(obj).items()}

    jm = {"card_motion.json": joints_map(cm),
          "motion_input.json": joints_map(mi),
          "motion_input_foe.json": joints_map(mif)}
    jm0 = {"card_motion.json": joints_map(cm0),
           "motion_input.json": joints_map(mi0),
           "motion_input_foe.json": joints_map(mif0)}

    diffs = {}
    for name, obj, obj0 in (("card_motion.json", cm, cm0),
                            ("motion_input.json", mi, mi0),
                            ("motion_input_foe.json", mif, mif0)):
        diffs[name] = diff_paths(obj0, obj)

    checks: dict[str, bool] = {}
    errors: dict[str, str] = {}

    def add(name: str, fn) -> None:
        try:
            checks[name] = bool(fn())
        except Exception as exc:  # noqa: BLE001
            errors[name] = repr(exc)
            checks[name] = False

    # ── A 上游报告自洽：不信 ok 字段 ──────────────────────────
    for k in ("diag", "scan", "tear", "layout", "decision",
              "micro2_tear", "baseline", "apply", "readback",
              "probe", "boards", "gates_before", "gates_after"):
        add(f"upstream_{k}_all_checks_true",
            lambda k=k: report_ok(reports[k]))
    add("all_checks_15_of_15_green", lambda: (
        reports["all_checks"]["result"] == "ALL GREEN"
        and reports["all_checks"]["total"]
        == len(reports["all_checks"]["checks"])
        and reports["all_checks"]["failed"] == []))
    add("all_checks_pose_probe_pass", lambda: any(
        r["name"] == "pose_probe" and r["ok"] is True
        for r in reports["all_checks"]["checks"]))

    # ── B 落盘真值 ────────────────────────────────────────────
    add("three_tables_11joints_synchronized", lambda: (
        jm["card_motion.json"] == jm["motion_input.json"]
        == jm["motion_input_foe.json"]))
    add("all_three_15_cards_284_frames", lambda: all(
        len(jm[n]) == 15
        and sum(len(v) for v in jm[n].values()) == 284
        for n in jm))
    add("mapping_still_atan_12_both", lambda: all(
        m["mapping"].get("leg_mode") == EXPECTED_MODE
        and m["mapping"]["leg_cap_deg"] == EXPECTED_CAP
        for m in (mi, mif)))
    add("mappings_unchanged_vs_backup", lambda: (
        mi["mapping"] == mi0["mapping"]
        and mif["mapping"] == mif0["mapping"]))
    add("arm_gains_unchanged", lambda: (
        mi["mapping"]["arm_gain_deg"]
        == mi0["mapping"]["arm_gain_deg"]))
    add("non_joint_metadata_unchanged_all_three", lambda: all(
        all(obj.get(k) == obj0.get(k)
            for k in obj0 if k not in ("cards", "motions"))
        for obj, obj0 in ((cm, cm0), (mi, mi0), (mif, mif0))))
    add("only_four_leg_joints_in_diff_paths", lambda: all(
        bool(ps) and all(
            p.startswith(("cards.", "motions."))
            and ".track[" in p
            and any(j in p for j in LEG_JOINTS)
            for p in ps)
        for ps in diffs.values()))
    add("diff_paths_bounded_by_edits", lambda: all(
        len(ps) <= landing["changed_frame_total"] * 4 * 2
        for ps in diffs.values()))
    add("all_track_endpoints_identical_to_backup", lambda: all(
        jm[n][c][0] == jm0[n][c][0]
        and jm[n][c][-1] == jm0[n][c][-1]
        for n in jm for c in jm[n]))
    add("landing_edits_all_present_in_shipped", lambda: all(
        all(
            all(tuple(all_tracks(obj)[card][int(i)][j]) == tuple(xy)
                for j, xy in vals.items())
            for i, vals in frames.items())
        for obj in (cm, mi, mif)
        for card, frames in landing["edits"].items()))
    add("three_shipped_sha_match_apply_report", lambda: all(
        sha(GAME / rel) == apply_rep["rows"][rel]["after_sha256"]
        for rel in TO_CHANGE))
    add("three_backups_match_baseline_sha", lambda: all(
        sha(ORIG / Path(rel).name)
        == reports["baseline"]["files"][rel]["sha256"]
        for rel in TO_CHANGE))
    add("eleven_watched_files_unchanged", lambda: all(
        sha(GAME / rel) == reports["baseline"]["files"][rel]["sha256"]
        for rel in apply_rep["untouched"]))
    add("apply_report_edits_per_file_matches_landing", lambda: (
        apply_rep["edit_count_per_file"]
        == sum(len(v) for f in landing["edits"].values()
               for v in f.values())))
    add("roundtrip_identity_still_holds_on_shipped", lambda: (
        (GAME / "data" / "card_motion.json").read_bytes()
        == json.dumps(cm, indent=1, ensure_ascii=False).replace(
            "\n", "\r\n").encode("utf-8")
        and (GAME / "data" / "motion_input.json").read_bytes()
        == (json.dumps(mi, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")))

    # ── C 独立重算：平台 / 位移 / delta ───────────────────────
    add("readback_exact_flat_zero", lambda: (
        reports["readback"]["agg"]["exact_flat_pairs"] == 0))
    add("readback_perceptual_below_baseline", lambda: (
        reports["readback"]["agg"]["perceptual_flat_pairs"]
        < reports["readback"]["scan_baseline"]["perceptual_flat_pairs"]))
    add("readback_agg_matches_landing_recomputed", lambda: (
        reports["readback"]["agg"] == landing["measure_recomputed"]))
    add("max_2d_displacement_under_2px", lambda: (
        reports["readback"]["agg"]["max_joint_delta_px"] < 2.0))
    add("diagnosed_native_pairs_are_255", lambda: (
        reports["diag"]["q2_pairs"]["exact_flat_pairs"] == 255))
    add("whole_frame_hold_pairs_are_224", lambda: (
        reports["diag"]["q2_pairs"]["whole_frame_identical_pairs"] == 224))
    add("baseline_perceptual_is_308", lambda: (
        reports["tear"]["per_case"]["baseline"]["perceptual_flat_pairs"]
        == 308))
    add("shipped_perceptual_below_308", lambda: (
        landing["measure_recomputed"]["perceptual_flat_pairs"] < 308))
    add("hybrid_rejected_for_33px", lambda: (
        reports["tear"]["per_case"]["hybrid"]["max_joint_delta_px"] > 30
        and "hybrid" in reports["decision"]["why_hybrid_rejected"]))
    add("landing_case_is_micro2", lambda: (
        landing["case"] == "micro_2"
        and landing["amplitude_px"] == 2.0))
    add("endpoint_protection_rule_recorded", lambda: (
        "首帧" in landing["build_rule"]
        and "末帧" in landing["build_rule"]
        and all(landing["protected_endpoints_identical"].values())))
    add("scan_recommended_hybrid_but_landed_micro2", lambda: (
        reports["scan"]["recommended_case"] == "hybrid_lerp_micro03"
        and reports["decision"]["decision"].startswith("落地 micro2")))
    add("endpoints_never_appear_in_changed_frames", lambda: all(
        0 not in landing["changed_frames"][c]
        and len(tracks("shipped")[c]) - 1
        not in landing["changed_frames"][c]
        for c in landing["changed_frames"]))

    # 13 骨 delta：逐行逐骨与引擎读回对账
    rows = probe["rows"]
    add("probe_rows_36", lambda: len(rows) == 36)
    add("probe_three_modes_12_frames", lambda: (
        {r["mode"] for r in rows} == {"shipped", "rolled_back",
                                      "reapplied"}
        and len({(r["card"], r["frame"]) for r in rows}) == 12))
    add("delta_13_bones_recomputed_all_rows_both_sides", lambda: all(
        (lambda exp: bool(exp) and all(
            abs(float(r[f"{side}_delta"].get(k, 1e9)) - exp[k]) < 1e-3
            for k in exp))(
                expected_delta(r["card"], r["frame"],
                               "rolled_back" if r["mode"] == "rolled_back"
                               else "shipped"))
        for r in rows for side in ("player", "foe")))
    add("shipped_and_rolled_back_table_markers_differ", lambda: (
        probe["shipped_marker_p"] != probe["legacy_marker_p"]
        and probe["checks"]["shipped_and_legacy_table_markers_differ"]
        is True))
    add("probe_all_checks_true", lambda: report_ok(probe))

    # ── D 引擎 A/B 与全量自检 ─────────────────────────────────
    for k in ("shipped_mapping_still_atan12",
              "table_marker_matches_every_scene",
              "delta_matches_python_formula_per_table",
              "all_action_deltas_differ_between_tables",
              "stance_untouched",
              "shipped_reapplied_identical_same_process",
              "action_pixel_diffs_majority",
              "two_d_readback_ok", "two_d_no_script_errors",
              "default_zero_pollution", "default_no_script_errors",
              "default_two_pngs", "all_sv_pngs_nonempty",
              "main_no_script_errors", "hp_unchanged",
              "all_action_frames_are_edited_frames"):
        add(f"probe_{k}", lambda k=k: probe["checks"][k] is True)
    add("probe_action_diffs_all_nonzero", lambda: (
        probe["action_diff_nonzero"] == probe["action_diff_total"]))
    add("two_d_max_displacement_matches_python", lambda: (
        abs(probe["two_d"]["payload"]["max_joint_delta_px"]
            - reports["readback"]["agg"]["max_joint_delta_px"]) < 1e-3))
    add("two_d_only_four_leg_joints_changed", lambda: (
        probe["two_d"]["payload"]["non_leg_changes"] == 0))

    # ── E 真实 GLB 撕裂成本 ───────────────────────────────────
    add("native_tear_852_poses", lambda: (
        reports["tear"]["poses_evaluated"] == 852
        and len(reports["tear"]["per_case"]) == 3))
    add("micro2_tear_284_poses", lambda: (
        reports["micro2_tear"]["poses_evaluated"] == 284))
    add("micro2_p999_within_external_anchor", lambda: (
        reports["micro2_tear"]["worst_p999_m"] <= P999_LIMIT_M))
    add("micro2_zero_frames_over_anchor", lambda: (
        reports["micro2_tear"]["frames_over_anchor"] == 0))
    add("micro2_p999_not_worse_than_baseline", lambda: (
        reports["micro2_tear"]["worst_p999_m"]
        <= reports["tear"]["per_case"]["baseline"]["worst_p999_m"]))
    add("micro2_p999_better_than_hybrid", lambda: (
        reports["micro2_tear"]["worst_p999_m"]
        < reports["tear"]["per_case"]["hybrid"]["worst_p999_m"]))
    add("pose_matrix_error_under_limit", lambda: (
        reports["micro2_tear"]["max_pose_matrix_err"] < POSE_ERR_LIMIT
        and reports["tear"]["max_pose_matrix_err"] < POSE_ERR_LIMIT))
    add("baseline_matches_p3_atan12", lambda: (
        reports["tear"]["per_case"]["baseline"]["worst_p999_m"]
        == reports["tear"]["p3_atan12_worst_p999_m"]))
    add("decision_cost_table_backfilled", lambda: (
        reports["decision"]["cost_table"]["micro_2"]["worst_p999_m"]
        == reports["micro2_tear"]["worst_p999_m"]))

    # ── F 看图产物 ────────────────────────────────────────────
    for name in BOARDS_EXPECTED:
        add(f"board_{name}_valid_png",
            lambda name=name: png_ok(BOARDS / name))
    add("three_new_boards_in_report", lambda: all(
        Path(v["path"]).is_file()
        for k, v in reports["boards"]["made"].items()
        if k in ("curve", "strip", "compare")))
    add("curve_focus_flat_reduced", lambda: (
        reports["boards"]["made"]["curve"]["shipped_flat_pairs_in_focus"]
        < reports["boards"]["made"]["curve"][
            "original_flat_pairs_in_focus"]))
    add("default_off_two_pngs_valid", lambda: all(
        png_ok(p, 100000) for p in sorted(
            (HERE / "shots" / "default_p4").glob("*.png")))
        and len(list((HERE / "shots" / "default_p4").glob("*.png"))) == 2)
    add("sv_shots_all_present", lambda: all(
        Path(r[f"{side}_sv"]).is_file()
        for r in rows for side in ("player", "foe")))

    # ── G 历史守卫债：实测、点名、还原 ────────────────────────
    before = {r["tag"]: r for r in reports["gates_before"]["rows"]}
    after = {r["tag"]: r for r in reports["gates_after"]["rows"]}
    add("history_before_three_red_one_green", lambda: (
        len(before["motion_p1"]["failed"]) == 3
        and len(before["motion_p2"]["failed"]) == 6
        and len(before["live_match"]["failed"]) == 1
        and len(before["plateau_p3"]["failed"]) == 0))
    add("history_new_reds_exactly_as_measured", lambda: (
        reports["gates_after"]["new_reds_vs_before"]
        == {k: sorted(v) for k, v in EXPECTED_NEW_REDS.items()}))
    add("history_all_reports_restored_bytewise", lambda: (
        all(r.get("restored_sha_equal") is True
            for r in reports["gates_before"]["rows"])
        and all(r.get("restored_sha_equal") is True
                for r in reports["gates_after"]["rows"])))
    add("history_no_verify_crashed", lambda: (
        reports["gates_before"]["checks"]["no_verify_crashed"] is True
        and reports["gates_after"]["checks"]["no_verify_crashed"] is True
        and reports["gates_before"]["checks"][
            "all_verdict_lines_present"] is True))
    add("history_p1_not_faked_by_missing_pil", lambda: (
        before["motion_p1"].get("traceback") is False
        and before["motion_p1"].get("rc") == 1
        and "original_three_unchanged_both"
        not in before["motion_p1"]["failed"]))
    add("history_p2_reds_unchanged_by_p4", lambda: (
        set(before["motion_p2"]["failed"])
        == set(after["motion_p2"]["failed"])))

    total, passed = len(checks), sum(checks.values())
    failed = [k for k, v in checks.items() if not v]
    report = {"checks": checks, "errors": errors, "total": total,
              "passed": passed, "failed": failed,
              "ok": passed == total and not errors and not failed}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"NATIVE_VERIFY {passed}/{total} "
          f"{'ALL GREEN' if report['ok'] else 'FAILED'}")
    for k in failed:
        print("  RED", k, errors.get(k, ""))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
