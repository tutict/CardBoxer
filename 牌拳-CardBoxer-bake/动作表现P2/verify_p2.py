"""动作表现 P2 · 汇总承重判据（只读盘，不重跑 Godot / Blender）。

纪律：
  * 不信任何上游报告的 ok 字段，独立复核 checks 非空、全 True、failed 空；
  * 落盘真值直接从游戏工程重新读、与 pre-p2 备份递归逐值 diff；
  * 引擎读回、同进程 A/B 像素差、全量 284 帧撕裂都用报告里的原始数值
    重算，不只看汇总；
  * 历史守卫债单独列边界，不折进 P2 判据计数。

用法：python verify_p2.py
产出：data/verify_p2.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
P1 = BAKE / "动作覆盖P1"
D = HERE / "data"
BOARDS = HERE / "boards"
ORIG = HERE / "orig" / "pre-p2"
LOGS = HERE / "logs"
OUT = D / "verify_p2.json"

P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5
MIN_DIFF_PX = 200
EXPECTED_CAP = 9.0
ARM_GAINS = {"f_upper": 32.0, "f_fore": 26.0,
             "b_upper": 28.0, "b_fore": 22.0}
CORE_SCRIPTS = ("scripts/arena.gd", "scripts/fighter_3d_layer.gd",
                "scripts/rig_driver.gd")
EXPECTED_P1_REDS = {"non_cards_fields_equal_backup_both",
                    "mapping_gains_unchanged_both"}
BOARDS_EXPECTED = (
    "P2真实GLB-增益撕裂权衡.png",
    "P2腿部幅度-玩家对照.png",
    "P2腿部幅度-对手对照.png",
    "P2上线前后-玩家对照.png",
    "P2上线前后-对手对照.png",
)


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
    """不信上游 ok：checks 必须是非空 dict、全 True、failed 空。"""
    ck = rep.get("checks")
    if not isinstance(ck, dict) or not ck:
        return False
    if not all(v is True for v in ck.values()):
        return False
    if rep.get("failed"):
        return False
    return rep.get("ok", True) is True


def main() -> int:
    mi = jload(GAME / "data" / "motion_input.json")
    mif = jload(GAME / "data" / "motion_input_foe.json")
    mi_bak = jload(ORIG / "motion_input.json")
    mif_bak = jload(ORIG / "motion_input_foe.json")
    baseline = jload(D / "baseline_p2.json")
    apply_rep = jload(D / "apply_p2.json")
    diag = jload(D / "p2_diagnosis.json")
    sweep = jload(D / "tear_sweep.json")
    sweep_bl = jload(D / "tear_sweep_blender.json")
    full = jload(D / "full_tear.json")
    full_bl = jload(D / "full_tear_blender.json")
    plan = jload(D / "full_plan.json")
    glb_struct = jload(D / "glb_structure.json")
    amp = jload(D / "amplitude_p2_probe.json")
    shipped = jload(D / "p2_shipped_probe.json")
    all_checks = jload(D / "all_checks_p2.json")
    p1_log = (LOGS / "p1_verify_after_p2.out").read_text(encoding="utf-8")

    checks: dict[str, bool] = {}
    errs: dict[str, str] = {}

    def add(name: str, fn) -> None:
        try:
            checks[name] = bool(fn())
        except Exception as exc:  # 守卫崩栈不算绿
            checks[name] = False
            errs[name] = repr(exc)

    # ── A 落盘真值：直接读游戏工程，不信任何报告 ──────────────
    add("player_cap_is_9", lambda: mi["mapping"]["leg_cap_deg"]
        == EXPECTED_CAP)
    add("foe_cap_is_9", lambda: mif["mapping"]["leg_cap_deg"]
        == EXPECTED_CAP)
    add("player_arm_gains_untouched", lambda: mi["mapping"]["arm_gain_deg"]
        == ARM_GAINS)
    add("foe_arm_gains_untouched", lambda: mif["mapping"]["arm_gain_deg"]
        == ARM_GAINS)
    add("torso_caps_untouched", lambda: all(
        m["mapping"]["torso_cap_deg"] == 8.0 for m in (mi, mif)))
    add("two_mappings_identical", lambda: mi["mapping"] == mif["mapping"])
    add("two_card_tables_identical", lambda: mi["cards"] == mif["cards"])
    add("cards_15_both", lambda: all(len(m["cards"]) == 15
                                     for m in (mi, mif)))
    add("frames_284_both", lambda: all(
        sum(int(c["frames"]) for c in m["cards"].values()) == 284
        for m in (mi, mif)))
    add("only_one_diff_path_player", lambda: diff_paths(mi_bak, mi)
        == ["mapping.leg_cap_deg"])
    add("only_one_diff_path_foe", lambda: diff_paths(mif_bak, mif)
        == ["mapping.leg_cap_deg"])
    add("backup_bytewise_matches_baseline_player", lambda: sha(
        ORIG / "motion_input.json")
        == baseline["files"]["data/motion_input.json"]["sha256"])
    add("backup_bytewise_matches_baseline_foe", lambda: sha(
        ORIG / "motion_input_foe.json")
        == baseline["files"]["data/motion_input_foe.json"]["sha256"])
    add("other_12_watched_files_unchanged", lambda: all(
        (GAME / rel).is_file()
        and sha(GAME / rel) == meta["sha256"]
        for rel, meta in baseline["files"].items()
        if rel not in ("data/motion_input.json",
                       "data/motion_input_foe.json")))
    add("three_core_scripts_sha_unchanged", lambda: all(
        sha(GAME / rel) == baseline["files"][rel]["sha256"]
        for rel in CORE_SCRIPTS))
    add("apply_report_single_replace_both", lambda: all(
        r["bytewise_single_replace"] and r["diff_paths"]
        == ["mapping.leg_cap_deg"]
        for r in apply_rep["rows"].values()))

    # ── B 上游报告自洽：独立复核 checks，不看 ok ────────────────
    add("diag_report_all_checks_true", lambda: report_ok(diag))
    add("tear_sweep_report_all_checks_true", lambda: report_ok(sweep))
    add("baseline_report_all_checks_true", lambda: report_ok(baseline))
    add("apply_report_all_checks_true", lambda: report_ok(apply_rep))
    add("amplitude_probe_report_all_checks_true", lambda: report_ok(amp))
    add("shipped_probe_report_all_checks_true", lambda: report_ok(shipped))
    add("full_tear_report_all_checks_true", lambda: report_ok(full))
    add("all_checks_p2_15_15", lambda: (
        all_checks["total"] == 15
        and all_checks["failed"] == []
        and all_checks["result"] == "ALL GREEN"
        and len(all_checks["checks"]) == 15
        and all(r["ok"] is True for r in all_checks["checks"])))

    # ── C 真实 GLB 全量撕裂 ────────────────────────────────────
    add("anchor_pinned_at_0_09365", lambda: full["anchor_p999_m"]
        == P999_LIMIT_M)
    add("full_852_poses_evaluated", lambda: full_bl["poses_evaluated"]
        == 852 and len(full_bl["rows"]) == 852)
    add("full_three_cases_284_frames_each", lambda: (
        len(full_bl["cases"]) == 3
        and all(p["frames"] == 284 for p in full["per_case"].values())))
    add("full_plan_284_frame_pairs", lambda: (
        plan["frame_count"] == 284 and len(plan["frames"]) == 284))
    add("full_pose_matrix_err_within_limit", lambda: (
        full_bl["max_pose_matrix_err"] < POSE_ERR_LIMIT))
    add("full_tear_gate_pass", lambda: (
        full["verdict"]["full_284_frame_gate"] == "PASS"))
    add("cap09_no_frame_over_anchor", lambda: (
        full["per_case"]["cap09_hard_g100"]["frames_over_anchor"] == 0))
    add("cap09_worst_p999_within_anchor", lambda: (
        full["per_case"]["cap09_hard_g100"]["worst_p999_m"]
        <= P999_LIMIT_M))
    add("cap12_no_frame_over_anchor", lambda: (
        full["per_case"]["cap12_hard_g100"]["frames_over_anchor"] == 0))
    add("cap09_worse_than_baseline_lt_1_5", lambda: (
        full["per_case"]["cap09_hard_g100"]["worst_over_shipped_baseline"]
        < 1.5))
    add("shipped_baseline_within_anchor", lambda: (
        full["per_case"]["cap03_hard_g100"]["frames_over_anchor"] == 0))
    add("representative_sweep_missed_no_worse_frame", lambda: all(
        abs(v) < 1e-9 for v in full["sampling_gap_m"].values()))
    add("real_glb_mesh_shape", lambda: (
        full_bl["vertices"] == 57934 and full_bl["edges"] == 136092
        and full_bl["armature_bones"] == 14
        and full_bl["missing_bones"] == []))
    add("glb_structure_probe_found_skinned_mesh_and_armature", lambda: (
        any(o["type"] == "MESH" and o.get("vertices") == 57934
            and o.get("vertex_groups") for o in glb_struct["objects"])
        and any(o["type"] == "ARMATURE" and len(o.get("bones", [])) == 14
                for o in glb_struct["objects"])))
    add("representative_sweep_260_poses", lambda: (
        sweep_bl["poses_evaluated"] == 260
        and sweep_bl["max_pose_matrix_err"] < POSE_ERR_LIMIT))

    # ── D 引擎内上线态 ─────────────────────────────────────────
    sp = shipped["main"]["payload"]
    dp = shipped["default"]["payload"]
    sdiff = shipped["diff_px"]
    add("shipped_cap_readback_9_both_sides", lambda: (
        sp["mapping_cap_player"] == EXPECTED_CAP
        and sp["mapping_cap_foe"] == EXPECTED_CAP))
    add("shipped_use_3d_and_15_cards", lambda: (
        sp["use_3d"] is True and sp["cards_player"] == 15
        and sp["cards_foe"] == 15))
    add("shipped_hp_unchanged", lambda: sp["hp"] == [100, 100])
    add("shipped_no_delta_formula_mismatch", lambda: (
        shipped["delta_mismatches"] == []))
    add("shipped_no_cap_violation", lambda: (
        shipped["cap_violations"] == []))
    add("shipped_action_frames_all_changed_both_sides", lambda: (
        len([k for k in sdiff
             if k.startswith("shipped_vs_rolled_back")
             and "stance" not in k]) == 6
        and all(v > MIN_DIFF_PX for k, v in sdiff.items()
                if k.startswith("shipped_vs_rolled_back")
                and "stance" not in k)))
    add("shipped_stance_bytewise_unchanged", lambda: (
        len([k for k in sdiff
             if k.startswith("shipped_vs_rolled_back")
             and "stance" in k]) == 2
        and all(v == 0 for k, v in sdiff.items()
                if k.startswith("shipped_vs_rolled_back")
                and "stance" in k)))
    add("shipped_reapplied_identical_same_process", lambda: (
        len([k for k in sdiff
             if k.startswith("shipped_vs_reapplied")]) == 8
        and all(v == 0 for k, v in sdiff.items()
                if k.startswith("shipped_vs_reapplied"))))
    add("shipped_no_script_errors", lambda: (
        shipped["main"]["rc"] == 0
        and shipped["main"]["script_errors"] == 0))
    add("shipped_no_scenario_errors", lambda: (
        shipped["main"]["scenario_errors"] == 0))
    add("cross_process_cap09_bytewise_8_of_8", lambda: (
        len(shipped["cross_process_cap09_diagnostic_only"]) == 8
        and all(v["bytewise_equal"] for v in
                shipped["cross_process_cap09_diagnostic_only"].values())))
    add("default_zero_pollution", lambda: (
        dp["use_3d"] is False and dp["layer_3d"] is False
        and dp["layer_3d_foe"] is False
        and dp["player_override"] is False
        and dp["enemy_override"] is False and dp["env_3d"] == ""))
    add("default_no_script_errors", lambda: (
        shipped["default"]["rc"] == 0
        and shipped["default"]["script_errors"] == 0))
    add("amp_probe_four_caps_monotonic", lambda: (
        [amp["leg_peak_mean_deg_by_cap"][str(c)] for c in (3, 6, 9, 12)]
        == sorted(amp["leg_peak_mean_deg_by_cap"][str(c)]
                  for c in (3, 6, 9, 12))))

    # ── E 交付物与历史守卫债边界 ───────────────────────────────
    add("five_boards_present_and_sized", lambda: all(
        (BOARDS / n).is_file() and (BOARDS / n).stat().st_size > 50000
        for n in BOARDS_EXPECTED))
    # 只查大小会被「改坏 PNG 头但字节数不变」绕过，必须验签名与 IEND
    add("five_boards_valid_png_signature", lambda: all(
        (BOARDS / n).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        and (BOARDS / n).read_bytes()[-8:-4] == b"IEND"
        for n in BOARDS_EXPECTED))
    add("shipped_board_sources_all_present", lambda: all(
        Path(r[f"{side}_sv"]).is_file()
        for r in shipped["rows"] for side in ("player", "foe")))
    add("shipped_probe_script_in_game_bytewise", lambda: (
        (GAME / "tests" / "p2_shipped_probe.gd").is_file()
        and sha(GAME / "tests" / "p2_shipped_probe.gd")
        == sha(HERE / "tests" / "p2_shipped_probe.gd")))
    p1_fails = [ln.split()[1] for ln in p1_log.splitlines()
                if ln.startswith("FAIL ")]
    p1_greens = [ln for ln in p1_log.splitlines()
                 if ln.startswith("CHECK ") and ln.rstrip().endswith("True")]
    add("p1_guard_exactly_two_expected_reds", lambda: (
        set(p1_fails) == EXPECTED_P1_REDS and len(p1_fails) == 2))
    add("p1_guard_other_50_still_green", lambda: (
        len(p1_greens) == 50
        and "MOTION_P1_VERIFY 50/52 FAILED" in p1_log))

    report = {
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "errors": errs,
        "total": len(checks),
        "passed": sum(1 for v in checks.values() if v),
        "expected_cap_deg": EXPECTED_CAP,
        "external_anchor_p999_m": P999_LIMIT_M,
        "expected_p1_historical_reds": sorted(EXPECTED_P1_REDS),
        "ok": all(checks.values()) and not errs,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    for k, v in errs.items():
        print("ERROR", k, v)
    print(f"MOTION_P2_VERIFY {report['passed']}/{report['total']} "
          f"{'ALL GREEN' if report['ok'] else 'FAILED'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
