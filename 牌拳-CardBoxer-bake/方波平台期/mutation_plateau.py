"""方波平台期 P3 · 变异验证：证明 verify_plateau.py 的 80 条判据有牙。

纪律（与 实跑一局/mutation_live.py 同款）：
  * 每组 needle 必须在目标文件里恰好命中 1 次；0 次 / 多次记
    DID NOT RUN 并计入「未证明」，绝不静默算通过。
  * CAUGHT 必须同时满足：verify 退出码非 0、报告可解析、ok=False、
    failed 非空、errors 为空（守卫靠崩栈变红不算证明），
    且点名的具体判据出现在 failed 里。
  * 变异体结构成立：JSON 仍可解析、GDScript 只改文本且语法仍成立、
    PNG 只改文件头字节。
  * 还原一律二进制写回 + sha256 证明；不靠退出码，不靠文本模式读写。
  * 子进程禁写字节码（PYTHONDONTWRITEBYTECODE=1）；
    clean re-run 必须全绿并把 verify_plateau.json 刷回绿色。
  * --selftest-dnr 故意用匹配不到的锚点，验证 DNR 分支确实会判未证明。

用法：python mutation_plateau.py [--only <子串>] [--selftest-dnr]
产出：data/mutation_plateau.json（selftest 写 mutation_plateau_dnr.json）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
D = HERE / "data"
BOARDS = HERE / "boards"
TESTS = HERE / "tests"
VERIFY = HERE / "verify_plateau.py"
VERIFY_OUT = D / "verify_plateau.json"
PY = sys.executable


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str, dict | None]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run([PY, "-B", str(VERIFY)], env=env,
                           capture_output=True, timeout=180,
                           cwd=str(HERE))
        rc = p.returncode
        text = (p.stdout + b"\n--- STDERR ---\n"
                + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    try:
        rep = json.loads(VERIFY_OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rep = None
    return rc, text, rep


def g(rel: str) -> Path:
    return GAME / rel


def cases() -> list[dict]:
    first_sv = json.loads((D / "p3_probe.json").read_text(
        encoding="utf-8"))["rows"][0]["player_sv"]
    return [
        # ── A 落盘真值：改游戏里的映射与驱动源码 ───────────────
        dict(name="M01_player_mode_to_hard",
             path=g("data/motion_input.json"),
             needle=b'"leg_mode":"atan"', mutant=b'"leg_mode":"hard"',
             expect=("player_mapping_atan_12",)),
        dict(name="M02_foe_mode_to_hard",
             path=g("data/motion_input_foe.json"),
             needle=b'"leg_mode":"atan"', mutant=b'"leg_mode":"hard"',
             expect=("foe_mapping_atan_12",)),
        dict(name="M03_player_cap_back_to_9",
             path=g("data/motion_input.json"),
             needle=b'"leg_cap_deg":12.0', mutant=b'"leg_cap_deg":9.0',
             expect=("player_mapping_atan_12",)),
        dict(name="M04_foe_cap_back_to_9",
             path=g("data/motion_input_foe.json"),
             needle=b'"leg_cap_deg":12.0', mutant=b'"leg_cap_deg":9.0',
             expect=("foe_mapping_atan_12",)),
        dict(name="M05_helper_signature_renamed",
             path=g("scripts/rig_driver.gd"),
             needle=b"func _leg(x: float", mutant=b"func _leg (x: float",
             expect=("rig_driver_helper_signature",)),
        dict(name="M06_atan_constant_changed",
             path=g("scripts/rig_driver.gd"),
             needle=b"cap * (2.0 / PI) * atan",
             mutant=b"cap * (1.0 / PI) * atan",
             expect=("atan_formula_constant_pinned",)),
        dict(name="M07_hard_fallback_removed",
             path=g("scripts/rig_driver.gd"),
             needle=b"return clampf(x, -cap, cap)", mutant=b"return x",
             expect=("legacy_fallback_clampf_present",)),
        dict(name="M08_legacy_default_flipped",
             path=g("scripts/rig_driver.gd"),
             needle=b'mapping.get("leg_mode", "hard")',
             mutant=b'mapping.get("leg_mode", "atan")',
             expect=("legacy_default_is_hard",)),
        dict(name="M09_one_leg_bone_skips_helper",
             path=g("scripts/rig_driver.gd"),
             needle=b'"thigh_f": _leg(', mutant=b'"thigh_f": clampf(',
             expect=("all_four_leg_bones_use_helper",
                     "no_inline_hard_clamp_left")),
        dict(name="M10_apply_single_replace_flipped",
             path=D / "apply_p3.json",
             needle=b'"bytewise_single_replace_each": true',
             mutant=b'"bytewise_single_replace_each": false',
             expect=("apply_report_three_single_replaces",)),
        dict(name="M11_baseline_check_flipped",
             path=D / "baseline_p3.json",
             needle=b'"three_backups_match_live_sha": true',
             mutant=b'"three_backups_match_live_sha": false',
             expect=("baseline_report_all_checks_true",)),
        dict(name="M12_watched_sha_tampered",
             path=D / "baseline_p3.json",
             needle=b"59fae145dc8696f2daea4800187ed66509c291697cfd5a0f6b6e"
                    b"f6942c7cd71a",
             mutant=b"59fae145dc8696f2daea4800187ed66509c291697cfd5a0f6b6e"
                    b"f6942c7cd71b",
             expect=("other_11_watched_files_unchanged",)),

        # ── B 上游报告自洽 ─────────────────────────────────────
        dict(name="M13_diag_check_flipped",
             path=D / "plateau_diagnosis.json",
             needle=b'"fifteen_tracks": true',
             mutant=b'"fifteen_tracks": false',
             expect=("diag_report_all_checks_true",)),
        dict(name="M14_tear_check_flipped",
             path=D / "plateau_tear.json",
             needle=b'"all_1420_poses_evaluated": true',
             mutant=b'"all_1420_poses_evaluated": false',
             expect=("tear_report_all_checks_true",)),
        dict(name="M15_probe_check_flipped",
             path=D / "p3_probe.json",
             needle=b'"main_marker_parsed": true',
             mutant=b'"main_marker_parsed": false',
             expect=("probe_report_all_checks_true",)),
        dict(name="M16_boards_check_flipped",
             path=D / "p3_boards.json",
             needle=b'"strip_32_panels": true',
             mutant=b'"strip_32_panels": false',
             expect=("boards_report_all_checks_true",)),
        dict(name="M17_all_checks_result_faked",
             path=D / "all_checks_p3.json",
             needle=b'"result": "ALL GREEN"', mutant=b'"result": "FAILED"',
             expect=("all_checks_p3_15_15",)),
        dict(name="M18_history_gate_check_flipped",
             path=D / "history_gates_p3.json",
             needle=b'"at_least_one_historical_red": true',
             mutant=b'"at_least_one_historical_red": false',
             expect=("history_gates_report_all_checks_true",)),

        # ── C 平台成因与诊断数字 ───────────────────────────────
        dict(name="M19_cause_split_broken",
             path=D / "plateau_diagnosis.json",
             needle=b'"exact_flat_from_clamp": 227',
             mutant=b'"exact_flat_from_clamp": 226',
             expect=("cause_split_sums_to_total",)),
        dict(name="M20_atan12_perceptual_flat_faked",
             path=D / "plateau_diagnosis.json",
             needle=b'"perceptual_flat_pairs": 308',
             mutant=b'"perceptual_flat_pairs": 500',
             expect=("atan12_perceptual_flat_below_hard09",
                     "atan_beats_tanh_on_perceptual_flatness")),
        # 诊断 JSON 由 write_text 在 Windows 落成 CRLF，多行 needle 必须
        # 带 \r\n；首版用 \n 命中 0 次被记 DNR，按纪律修到实测命中 1 次。
        dict(name="M21_live_action_plateau_faked",
             path=D / "plateau_diagnosis.json",
             needle=(b'"action_exact_flat_pairs": 13,\r\n'
                     b'      "longest_action_flat_run_pairs": 3,\r\n'
                     b'      "mean_peak_deg": 3.2163'),
             mutant=(b'"action_exact_flat_pairs": 35,\r\n'
                     b'      "longest_action_flat_run_pairs": 3,\r\n'
                     b'      "mean_peak_deg": 3.2163'),
             expect=("live_action_plateau_reduced",)),
        dict(name="M39_live_distinct_faked",
             path=D / "plateau_diagnosis.json",
             needle=b'"distinct_values": 7',
             mutant=b'"distinct_values": 22',
             expect=("live_distinct_values_increased",)),
        dict(name="M22_recommendation_swapped",
             path=D / "plateau_tear.json",
             needle=b'"recommended_case": "atan12"',
             mutant=b'"recommended_case": "tanh12"',
             expect=("recommendation_rule_recomputed_is_atan12",
                     "recommended_matches_shipped_mapping")),
        dict(name="M23_atan12_sampling_gap_injected",
             path=D / "plateau_tear.json",
             needle=b'"atan12": 0.0', mutant=b'"atan12": 0.5',
             expect=("representative_sampling_gap_all_zero",)),
        dict(name="M24_atan12_tear_over_anchor",
             path=D / "plateau_tear.json",
             needle=b'"worst_p999_m": 0.042737',
             mutant=b'"worst_p999_m": 0.099999',
             expect=("all_candidates_within_anchor",
                     "atan12_worst_p999_below_hard09_baseline")),
        dict(name="M25_atan12_leg_peak_mean_tampered",
             path=D / "plateau_tear.json",
             needle=b'"leg_peak_mean_deg": 6.7178',
             mutant=b'"leg_peak_mean_deg": 3.0000',
             expect=("atan12_leg_peak_mean_closest_to_baseline",)),
        dict(name="M26_full_pose_count_dropped",
             path=D / "full_tear_blender.json",
             needle=b'"poses_evaluated": 1420',
             mutant=b'"poses_evaluated": 1419',
             expect=("full_1420_poses_evaluated",)),
        dict(name="M27_plan_frame_count_dropped",
             path=D / "plateau_plan.json",
             needle=b'"frame_count": 284', mutant=b'"frame_count": 283',
             expect=("plan_5_cases_284_frames_1420_poses",)),
        dict(name="M28_baseline_platform_count_tampered",
             path=D / "plateau_tear.json",
             needle=b'"exact_flat_pairs": 482',
             mutant=b'"exact_flat_pairs": 400',
             expect=("hard09_platform_count_matches_tear",)),

        # ── D 引擎内 A/B 与交付物 ──────────────────────────────
        dict(name="M29_shipped_readback_faked",
             path=D / "p3_probe.json",
             needle=b'"mapping_mode_player": "atan"',
             mutant=b'"mapping_mode_player": "hard"',
             expect=("shipped_readback_atan_12_both_sides",)),
        dict(name="M30_stance_no_longer_zero",
             path=D / "p3_probe.json",
             needle=b'"shipped_vs_rolled_back:stance00:player": 0',
             mutant=b'"shipped_vs_rolled_back:stance00:player": 12',
             expect=("stance_untouched_pixel_zero",)),
        dict(name="M31_reapplied_no_longer_identical",
             path=D / "p3_probe.json",
             needle=b'"shipped_vs_reapplied:stance00:player": 0',
             mutant=b'"shipped_vs_reapplied:stance00:player": 5',
             expect=("shipped_reapplied_identical_same_process",)),
        dict(name="M32_probe_script_out_of_sync",
             path=TESTS / "p3_plateau_probe.gd",
             needle=b'return ["shipped", "rolled_back", "reapplied", '
                    b'"legacy_compat"]',
             mutant=b'return ["shipped", "rolled_back", "reapplied_x", '
                    b'"legacy_compat"]',
             expect=("probe_script_bytewise_in_game",)),
        dict(name="M33_sv_png_signature_broken",
             path=Path(first_sv),
             needle=b"\x89PNG\r\n\x1a\n", mutant=b"\x89PNG\r\n\x1a\x00",
             expect=("all_96_sv_pngs_valid_signature",)),
        dict(name="M34_timeline_png_signature_broken",
             path=BOARDS / "P3-时间线方波.png",
             needle=b"\x89PNG\r\n\x1a\n", mutant=b"\x89PNG\r\n\x1a\x00",
             expect=("four_boards_valid_png_signature",)),
        dict(name="M35_timeline_flat_stat_tampered",
             path=D / "p3_boards.json",
             needle=b'"hard9_flat_pairs": 107',
             mutant=b'"hard9_flat_pairs": 999',
             expect=("timeline_flat_stats_independently_recomputed",)),
        dict(name="M36_timeline_sample_count_tampered",
             path=D / "p3_boards.json",
             needle=b'"samples": 129', mutant=b'"samples": 128',
             expect=("timeline_129_real_samples",)),

        # ── E 历史守卫债边界 ───────────────────────────────────
        dict(name="M37_history_red_name_renamed",
             path=D / "history_gates_p3.json",
             needle=b'"ten_untouched_unchanged"',
             mutant=b'"ten_untouched_unchanged_x"',
             expect=("history_reds_exactly_ten_expected_entries",)),
        dict(name="M38_history_restore_proof_flipped",
             path=D / "history_gates_p3.json",
             needle=b'"all_three_restored_bytewise": true',
             mutant=b'"all_three_restored_bytewise": false',
             expect=("history_gates_report_all_checks_true",)),
    ]


def main() -> int:
    selftest = "--selftest-dnr" in sys.argv
    out = D / ("mutation_plateau_dnr.json" if selftest
               else "mutation_plateau.json")
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if selftest:
        cs = [dict(name="SELFTEST_DNR", path=D / "plateau_tear.json",
                   needle=b"NEVER_MATCH_PLATEAU_ANCHOR_XYZ", mutant=b"X",
                   expect=("anchor_pinned_at_0_09365",))]
    else:
        cs = cases()
        if only:
            cs = [c for c in cs if only.lower() in c["name"].lower()]

    originals: dict[Path, bytes] = {}
    for c in cs:
        p = Path(c["path"])
        if p not in originals:
            if not p.is_file():
                print("MISSING", p)
                return 1
            originals[p] = p.read_bytes()

    rows = []
    for c in cs:
        p = Path(c["path"])
        b = originals[p]
        n = b.count(c["needle"])
        if n != 1:
            rows.append({"name": c["name"], "status": "DID NOT RUN",
                         "needle_count": n, "path": str(p),
                         "restored": sha(p.read_bytes()) == sha(b)})
            print("DNR", c["name"], "needle_count", n)
            continue
        try:
            p.write_bytes(b.replace(c["needle"], c["mutant"], 1))
            rc, text, rep = run_verify()
        finally:
            p.write_bytes(b)  # 无条件二进制还原
        restored = sha(p.read_bytes()) == sha(b)
        failed = rep.get("failed", []) if isinstance(rep, dict) else []
        errors = rep.get("errors", {}) if isinstance(rep, dict) else {}
        hit = [e for e in c["expect"] if e in failed]
        caught = (rc != 0 and isinstance(rep, dict)
                  and rep.get("ok") is False
                  and len(failed) >= 1
                  and not errors
                  and bool(hit))
        status = "CAUGHT" if caught else "MISSED"
        rows.append({"name": c["name"], "status": status,
                     "path": str(p), "rc": rc, "restored": restored,
                     "expect_any": list(c["expect"]), "expect_hit": hit,
                     "failed": failed, "errors": errors,
                     "verify_tail": text.strip().splitlines()[-3:]})
        print(status, c["name"], "rc", rc, "restore", restored,
              "hit", hit, "errors", errors)

    restore_all = {str(p): sha(p.read_bytes()) == sha(b)
                   for p, b in originals.items()}
    crc, ctext, crep = run_verify()
    clean_green = (crc == 0 and isinstance(crep, dict)
                   and crep.get("ok") is True
                   and crep.get("failed") == []
                   and crep.get("errors") == {}
                   and "ALL GREEN" in ctext)
    proven = (all(r["status"] == "CAUGHT" for r in rows)
              and all(restore_all.values()) and clean_green)
    if selftest:
        proven = False
    report = {
        "cases": len(rows),
        "caught": sum(1 for r in rows if r["status"] == "CAUGHT"),
        "dnr": sum(1 for r in rows if r["status"] == "DID NOT RUN"),
        "missed": sum(1 for r in rows if r["status"] == "MISSED"),
        "restored": sum(1 for r in rows if r.get("restored")),
        "files_restored": restore_all,
        "clean_green": clean_green,
        "clean_verify": crep.get("passed") if isinstance(crep, dict) else None,
        "clean_verify_total": crep.get("total") if isinstance(crep, dict)
        else None,
        "selftest_dnr": selftest,
        "rows": rows, "ok": proven,
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"MUTATION_PLATEAU {report['caught']}/{report['cases']} CAUGHT / "
          f"DNR {report['dnr']} / MISSED {report['missed']} / "
          f"RESTORE {report['restored']}/{report['cases']} / "
          f"clean {report['clean_verify']}/{report['clean_verify_total']} "
          f"{'ALL GREEN' if clean_green else 'FAILED'}")
    if selftest:
        print("SELFTEST_DNR_EFFECTIVE" if report["dnr"] == 1
              and not proven else "SELFTEST_DNR_INEFFECTIVE")
        print("MUTATION_PLATEAU_FAILED (by design)")
        return 1
    print("MUTATION_PLATEAU_OK" if proven else "MUTATION_PLATEAU_FAILED")
    return 0 if proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
