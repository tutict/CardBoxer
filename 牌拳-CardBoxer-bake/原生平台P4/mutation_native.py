"""原生平台 P4 · 变异验证：证明 verify_native.py 的判据有牙。

纪律（与 P3 / B 路线同款，并针对本机踩过的坑收紧）：
  * needle 一律**单行 ASCII bytes**，不用多行 needle（CRLF 会让 \n 锚点
    命中 0 次），不用 bytes 字面量里的中文；
  * needle 必须在目标文件里恰好命中 1 次；0 次 / 多次记 DID NOT RUN
    并计入「未证明」，绝不静默算通过；
  * CAUGHT 必须同时满足：verify 退出码非 0、报告可解析、ok=False、
    failed 非空、errors 为空（守卫靠崩栈变红不算证明），
    且点名的具体判据至少有一条出现在 failed 里；
  * 变异体结构成立：JSON 仍可解析；PNG 只在文件尾追加字节（签名仍在）；
  * 还原一律二进制写回 + sha256 证明，不靠退出码、不靠文本模式读写；
  * 子进程禁写字节码（PYTHONDONTWRITEBYTECODE=1）；
  * clean re-run 必须全绿，把 verify_native.json 刷回绿色；
  * --selftest-dnr 故意用匹配不到的锚点，验证 DNR 分支确实会判未证明。

用法：python mutation_native.py [--only <子串>] [--selftest-dnr]
产出：data/mutation_native.json（selftest 写 mutation_native_dnr.json）
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
VERIFY = HERE / "verify_native.py"
VERIFY_OUT = D / "verify_native.json"
PY = sys.executable


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str, dict | None]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run([PY, "-B", str(VERIFY)], env=env,
                           capture_output=True, timeout=240,
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
    return [
        # ── A 落盘真值（改游戏工程里的三份表）─────────────────
        dict(name="M01_player_mode_to_hard",
             path=g("data/motion_input.json"),
             needle=b'"leg_mode":"atan"', mutant=b'"leg_mode":"hard"',
             expect=("mapping_still_atan_12_both",
                     "mappings_unchanged_vs_backup")),
        dict(name="M02_foe_cap_back_to_9",
             path=g("data/motion_input_foe.json"),
             needle=b'"leg_cap_deg":12.0', mutant=b'"leg_cap_deg":9.0',
             expect=("mapping_still_atan_12_both",
                     "mappings_unchanged_vs_backup")),
        dict(name="M03_foe_mode_to_hard",
             path=g("data/motion_input_foe.json"),
             needle=b'"leg_mode":"atan"', mutant=b'"leg_mode":"hard"',
             expect=("mapping_still_atan_12_both",)),
        dict(name="M04_arm_gain_tampered",
             path=g("data/motion_input.json"),
             needle=b'"f_upper":32.0', mutant=b'"f_upper":33.0',
             expect=("arm_gains_unchanged",
                     "mappings_unchanged_vs_backup")),
        dict(name="M05_card_motion_units_tampered",
             path=g("data/card_motion.json"),
             needle=b'"units": "game px; origin at the feet; +x forward; -y up"',
             mutant=b'"units": "game px; origin at the feet; +x forward; -y UP"',
             expect=("non_joint_metadata_unchanged_all_three",
                     "three_shipped_sha_match_apply_report",
                     "roundtrip_identity_still_holds_on_shipped")),
        dict(name="M06_mi_source_tampered",
             path=g("data/motion_input.json"),
             needle=b'"source":"baked2.json"',
             mutant=b'"source":"bakedX.json"',
             expect=("non_joint_metadata_unchanged_all_three",)),

        # ── B 上游报告自洽 ─────────────────────────────────────
        dict(name="M07_apply_check_flipped",
             path=D / "apply_native.json",
             needle=b'"baseline_ok": true', mutant=b'"baseline_ok": false',
             expect=("upstream_apply_all_checks_true",)),
        dict(name="M08_readback_check_flipped",
             path=D / "readback_native.json",
             needle=b'"exact_flat_pairs_zero": true',
             mutant=b'"exact_flat_pairs_zero": false',
             expect=("upstream_readback_all_checks_true",)),
        dict(name="M09_probe_check_flipped",
             path=D / "p4_probe.json",
             needle=b'"main_marker_parsed": true',
             mutant=b'"main_marker_parsed": false',
             expect=("upstream_probe_all_checks_true",)),
        dict(name="M10_boards_check_flipped",
             path=D / "p4_boards.json",
             needle=b'"curve_flat_reduced_in_focus": true',
             mutant=b'"curve_flat_reduced_in_focus": false',
             expect=("upstream_boards_all_checks_true",)),
        dict(name="M11_all_checks_result_faked",
             path=D / "all_checks_p4.json",
             needle=b'"result": "ALL GREEN"',
             mutant=b'"result": "FAILED"',
             expect=("all_checks_15_of_15_green",)),
        dict(name="M12_baseline_check_flipped",
             path=D / "baseline_p4.json",
             needle=b'"three_backups_match_live_sha": true',
             mutant=b'"three_backups_match_live_sha": false',
             expect=("upstream_baseline_all_checks_true",)),
        dict(name="M13_layout_check_flipped",
             path=D / "layout_probe.json",
             needle=b'"three_tables_11joints_identical": true',
             mutant=b'"three_tables_11joints_identical": false',
             expect=("upstream_layout_all_checks_true",)),
        dict(name="M14_gates_before_crash_gate_flipped",
             path=D / "history_gates_p4_before.json",
             needle=b'"no_verify_crashed": true',
             mutant=b'"no_verify_crashed": false',
             expect=("upstream_gates_before_all_checks_true",
                     "history_no_verify_crashed")),
        dict(name="M15_gates_after_crash_gate_flipped",
             path=D / "history_gates_p4_after.json",
             needle=b'"no_verify_crashed": true',
             mutant=b'"no_verify_crashed": false',
             expect=("upstream_gates_after_all_checks_true",
                     "history_no_verify_crashed")),

        # ── C 决策 / 落地数据 ──────────────────────────────────
        dict(name="M16_landing_case_renamed",
             path=D / "landing_tracks.json",
             needle=b'"case": "micro_2"', mutant=b'"case": "micro_05"',
             expect=("landing_case_is_micro2",)),
        dict(name="M17_amplitude_tampered",
             path=D / "landing_tracks.json",
             needle=b'"amplitude_px": 2.0', mutant=b'"amplitude_px": 3.0',
             expect=("landing_case_is_micro2",)),
        dict(name="M18_decision_prefix_broken",
             path=D / "landing_decision.json",
             needle=b'"decision": "', mutant=b'"decision": "X',
             expect=("scan_recommended_hybrid_but_landed_micro2",)),
        dict(name="M19_endpoint_protection_flipped",
             path=D / "landing_tracks.json",
             needle=b'"backstep": true', mutant=b'"backstep": false',
             expect=("endpoint_protection_rule_recorded",)),
        dict(name="M20_scan_recommendation_rewritten",
             path=D / "candidate_scan.json",
             needle=b'"recommended_case": "hybrid_lerp_micro03"',
             mutant=b'"recommended_case": "micro_2"',
             expect=("scan_recommended_hybrid_but_landed_micro2",)),
        dict(name="M21_cost_table_backfill_removed",
             path=D / "landing_decision.json",
             needle=b'"worst_p999_m": 0.042681',
             mutant=b'"worst_p999_m": null',
             expect=("decision_cost_table_backfilled",)),

        # ── D 诊断 / 撕裂 ──────────────────────────────────────
        dict(name="M22_whole_frame_hold_count_tampered",
             path=D / "native_diagnosis.json",
             needle=b'"whole_frame_identical_pairs": 224',
             mutant=b'"whole_frame_identical_pairs": 223',
             expect=("whole_frame_hold_pairs_are_224",)),
        dict(name="M23_native_tear_pose_count_tampered",
             path=D / "native_tear.json",
             needle=b'"poses_evaluated": 852',
             mutant=b'"poses_evaluated": 851',
             expect=("native_tear_852_poses",)),
        dict(name="M24_p3_anchor_tampered",
             path=D / "native_tear.json",
             needle=b'"p3_atan12_worst_p999_m": 0.042737',
             mutant=b'"p3_atan12_worst_p999_m": 0.05',
             expect=("baseline_matches_p3_atan12",)),
        dict(name="M25_micro2_over_anchor_frames_faked",
             path=D / "micro2_tear.json",
             needle=b'"frames_over_anchor": 0',
             mutant=b'"frames_over_anchor": 1',
             expect=("micro2_zero_frames_over_anchor",)),
        dict(name="M26_micro2_p999_inflated",
             path=D / "micro2_tear.json",
             needle=b'"worst_p999_m": 0.042681',
             mutant=b'"worst_p999_m": 0.05',
             expect=("micro2_p999_not_worse_than_baseline",
                     "micro2_p999_better_than_hybrid",
                     "decision_cost_table_backfilled")),
        dict(name="M27_micro2_pose_count_tampered",
             path=D / "micro2_tear.json",
             needle=b'"poses_evaluated": 284',
             mutant=b'"poses_evaluated": 283',
             expect=("micro2_tear_284_poses",)),

        # ── E 引擎 A/B 与 2D 读回 ──────────────────────────────
        dict(name="M28_stance_guard_flipped",
             path=D / "p4_probe.json",
             needle=b'"stance_untouched": true',
             mutant=b'"stance_untouched": false',
             expect=("probe_stance_untouched",)),
        dict(name="M29_action_diff_count_tampered",
             path=D / "p4_probe.json",
             needle=b'"action_diff_nonzero": 22',
             mutant=b'"action_diff_nonzero": 21',
             expect=("probe_action_diffs_all_nonzero",)),
        dict(name="M30_two_d_non_leg_change_faked",
             path=D / "p4_probe.json",
             needle=b'"non_leg_changes": 0',
             mutant=b'"non_leg_changes": 1',
             expect=("two_d_only_four_leg_joints_changed",)),
        dict(name="M31_two_d_displacement_inflated",
             path=D / "p4_probe.json",
             needle=b'"max_joint_delta_px": 1.7778',
             mutant=b'"max_joint_delta_px": 9.9999',
             expect=("two_d_max_displacement_matches_python",
                     "two_d_readback_ok")),

        # ── F 看图产物：只追加尾字节，PNG 签名仍在 ────────────
        dict(name="M32_curve_board_png_tail_appended",
             path=BOARDS / "P4-平台曲线对照.png",
             needle=b"", mutant=b"\x00\x00\x00\x00", mode="append",
             expect=("board_P4-平台曲线对照.png_valid_png",)),
    ]


def mutant_valid(path: Path, data: bytes) -> bool:
    if path.suffix == ".json":
        try:
            json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        return True
    if path.suffix == ".png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    return True


def main() -> int:
    selftest = "--selftest-dnr" in sys.argv
    only = ""
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1].lower()

    if selftest:
        pool = [dict(name="DNR_SELFTEST", path=D / "landing_tracks.json",
                     needle=b"THIS_ANCHOR_DOES_NOT_EXIST_9f3a",
                     mutant=b"whatever",
                     expect=("landing_case_is_micro2",))]
    else:
        pool = [c for c in cases() if not only or only in c["name"].lower()]

    rows = []
    for c in pool:
        path = Path(c["path"])
        rec = {"name": c["name"], "path": str(path),
               "expect": list(c["expect"])}
        if not path.is_file():
            rec.update(status="DID NOT RUN", why="missing file")
            rows.append(rec)
            continue
        original = path.read_bytes()
        needle, mutant = c["needle"], c["mutant"]
        if c.get("mode") == "append":
            changed = original + mutant
            n = 1
        else:
            n = original.count(needle)
            changed = (original.replace(needle, mutant, 1)
                       if n == 1 else original)
        rec["anchor_hits"] = n
        if n != 1:
            rec.update(status="DID NOT RUN", why=f"anchor hits {n}")
            rows.append(rec)
            continue
        if not mutant_valid(path, changed):
            rec.update(status="BROKEN MUTANT", why="structure invalid")
            rows.append(rec)
            continue
        try:
            path.write_bytes(changed)
            rc, text, rep = run_verify()
        finally:
            path.write_bytes(original)
        rec["restored"] = sha(path.read_bytes()) == sha(original)
        failed = list(rep.get("failed", [])) if rep else []
        errors = rep.get("errors", {}) if rep else {"<no report>": "missing"}
        ok = (rc != 0 and rep is not None
              and rep.get("ok") is False
              and bool(failed) and not errors
              and any(k in failed for k in c["expect"])
              and rec["restored"])
        rec.update(rc=rc, verify_failed=failed[:12],
                   verify_errors=errors, status="CAUGHT" if ok else "MISSED")
        rows.append(rec)
        print(f"{c['name']:42s} {rec['status']:14s} "
              f"restore={rec['restored']} "
              f"red={','.join(failed[:3])}", flush=True)

    # clean re-run：把 verify_native.json 刷回绿色
    rc, text, rep = run_verify()
    clean_ok = (rc == 0 and rep is not None
                and rep.get("ok") is True
                and rep.get("passed") == rep.get("total")
                and not rep.get("failed") and not rep.get("errors"))
    caught = sum(r["status"] == "CAUGHT" for r in rows)
    dnr = sum(r["status"] == "DID NOT RUN" for r in rows)
    broken = sum(r["status"] == "BROKEN MUTANT" for r in rows)
    missed = sum(r["status"] == "MISSED" for r in rows)
    restored = sum(r.get("restored") is True for r in rows)
    ok = (not selftest and len(rows) > 0 and caught == len(rows)
          and dnr == 0 and broken == 0 and missed == 0
          and restored == len(rows) and clean_ok)
    selftest_ok = (selftest and dnr == len(rows) and len(rows) > 0
                   and clean_ok is True)
    report = {"cases": len(rows), "caught": caught, "dnr": dnr,
              "broken": broken, "missed": missed, "restored": restored,
              "clean_ok": clean_ok,
              "clean_passed": rep.get("passed") if rep else None,
              "clean_total": rep.get("total") if rep else None,
              "selftest": selftest, "only": only, "rows": rows,
              "ok": bool(ok or selftest_ok)}
    out = (D / "mutation_native_dnr.json" if selftest
           else D / "mutation_native.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"MUTATION_NATIVE {caught}/{len(rows)} CAUGHT / DNR {dnr} / "
          f"BROKEN {broken} / MISSED {missed} / RESTORE {restored}/{len(rows)}"
          f" / clean {report['clean_passed']}/{report['clean_total']} "
          f"{'ALL GREEN' if clean_ok else 'FAILED'}")
    if selftest:
        print("SELFTEST_DNR_EFFECTIVE" if selftest_ok
              else "SELFTEST_DNR_INEFFECTIVE")
        return 0 if selftest_ok else 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
