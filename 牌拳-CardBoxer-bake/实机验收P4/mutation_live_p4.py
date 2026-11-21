"""P4 · 实机验收 · 变异验证（证明 60 条承重判据真的有牙）。

纪律（沿用 P3 / P4 的 mutation harness）：
  * 锚点必须恰好命中 1 次，命中 0 次是 DID NOT RUN，计入未证明；
  * 变异体必须语法成立；守卫崩栈是 BROKEN，不算 CAUGHT；
  * 还原用二进制写回 + sha256 证明，不用 read_text/write_text（会换行转换）；
  * needle / mutant 一律单行 ASCII bytes，避开 CRLF 多行锚点与中文
    bytes 字面量；探针源码按文件行尾自适应；
  * 守卫子进程禁写字节码（PYTHONDONTWRITEBYTECODE=1），避免陈旧
    pyc 在同秒同 size 时被误用；
  * clean re-run 必须回到 60/60 ALL GREEN。

用法：python mutation_live_p4.py [--selftest-dnr]
产出：data/mutation_live_p4.json（或 data/mutation_live_p4_dnr.json）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
VERIFY = HERE / "verify_live_p4.py"
OUT = D / "mutation_live_p4.json"

CASES = [
    # ── 上游 run 报告（checks 翻 false / 数值篡改 / mismatches）──
    ("M01_live_paused_check_flipped", "data/live_p4.json",
     b'"three_d_paused_never_true": true',
     b'"three_d_paused_never_true": false',
     ["upstream_live_all_green"]),
    ("M02_live_no_modified_check_flipped", "data/live_p4.json",
     b'"no_monitored_game_file_modified": true',
     b'"no_monitored_game_file_modified": false',
     ["upstream_live_all_green"]),
    ("M03_marker_2d_value_tampered", "data/live_p4.json",
     b'"want_2d_shipped": "46.533333|-39.511111"',
     b'"want_2d_shipped": "46.533333|-39.511112"',
     ["marker_2d_shipped_both"]),
    ("M04_marker_mismatches_faked", "data/live_p4.json",
     b'"marker_mismatches": []', b'"marker_mismatches": [["x"]]',
     ["marker_rows_all_match_shipped"]),
    ("M05_delta_mismatches_faked", "data/live_p4.json",
     b'"delta_mismatches": []', b'"delta_mismatches": [["x"]]',
     ["engine_delta_matches_shipped"]),
    ("M06_live_failed_faked", "data/live_p4.json",
     b'"failed": []', b'"failed": ["x"]',
     ["upstream_live_all_green", "upstream_three_reports_have_no_failed"]),
    # ── 同源复算报告 ──
    ("M07_static_bound_deflated", "data/live_p4_analysis.json",
     b'"max_abs_delta_diff_deg": 1.870037',
     b'"max_abs_delta_diff_deg": 0.000001',
     ["live_delta_diff_within_static_bound"]),
    ("M08_live_diff_inflated", "data/live_p4_analysis.json",
     b'"live_max_abs_delta_diff_deg": 1.653096',
     b'"live_max_abs_delta_diff_deg": 9.999999',
     ["live_delta_diff_within_static_bound"]),
    ("M09_analysis_check_flipped", "data/live_p4_analysis.json",
     b'"framewise_pixel_ab_explicitly_not_applicable": true',
     b'"framewise_pixel_ab_explicitly_not_applicable": false',
     ["upstream_analysis_all_green"]),
    ("M10_phase_violations_faked", "data/live_p4_analysis.json",
     b'"phase_duration_violations": []',
     b'"phase_duration_violations": [["x"]]',
     ["phase_durations_within_spec"]),
    ("M11_stance_violations_faked", "data/live_p4_analysis.json",
     b'"stance_violations": []', b'"stance_violations": [["x"]]',
     ["stance_delta_zero_both_tables"]),
    ("M12_engine_delta_mismatches_faked", "data/live_p4_analysis.json",
     b'"engine_delta_mismatches": []',
     b'"engine_delta_mismatches": [["x"]]',
     ["engine_delta_matches_shipped"]),
    ("M13_sample_count_tampered", "data/live_p4_analysis.json",
     b'"sample_count": 128', b'"sample_count": 127',
     ["analysis_sample_count_equals_live_rows",
      "curves_cover_all_rows_both_tables"]),
    ("M14_analysis_failed_faked", "data/live_p4_analysis.json",
     b'"failed": []', b'"failed": ["x"]',
     ["upstream_analysis_all_green",
      "upstream_three_reports_have_no_failed"]),
    # ── 板材报告 ──
    ("M15_boards_check_flipped", "data/boards_p4.json",
     b'"three_boards_valid_png_signature": true',
     b'"three_boards_valid_png_signature": false',
     ["upstream_boards_all_green"]),
    ("M16_zoom_check_flipped", "data/boards_p4.json",
     b'"timeline_zoom_is_single_continuous_segment": true',
     b'"timeline_zoom_is_single_continuous_segment": false',
     ["upstream_boards_all_green"]),
    ("M17_board_sha_tampered", "data/boards_p4.json",
     b'"sha256": "30c5e01fc7a7f8782b6eb7a98e37c985b4959b6313d0e2d00fdd95251a2949d2"',
     b'"sha256": "30c5e01fc7a7f8782b6eb7a98e37c985b4959b6313d0e2d00fdd95251a2949d3"',
     ["three_boards_sha_match_report"]),
    ("M18_boards_failed_faked", "data/boards_p4.json",
     b'"failed": []', b'"failed": ["x"]',
     ["upstream_boards_all_green",
      "upstream_three_reports_have_no_failed"]),
    ("M20_all_checks_result_faked", "data/all_checks_live_p4.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"',
     ["all_checks_15_of_15_green"]),
    ("M21_all_checks_failed_faked", "data/all_checks_live_p4.json",
     b'"failed": []', b'"failed": ["pose_probe"]',
     ["all_checks_15_of_15_green"]),
    ("M22_sha_baseline_game_tampered", "data/sha_baseline.json",
     b'"game": "C:', b'"game": "D:',
     ["sha_baseline_matches_runner"]),
    ("M23_raw_log_script_error", "logs/godot_p4_live_three_d.log",
     b"--- STDERR ---", b"--- STDERR --- SCRIPT ERROR",
     ["both_no_script_errors_raw_logs"]),
    # ── 探针源码形状（「实机」的定义）──
    ("M24_probe_freezes_arena", "tests/p4_live_probe.gd",
     b"\t\tif bool(arena.paused):",
     b"\t\tarena.paused = true\n\t\tif bool(arena.paused):",
     ["probe_code_never_freezes_arena",
      "probe_copy_matches_game_deployed"]),
    ("M25_probe_drops_frame_wait", "tests/p4_live_probe.gd",
     b"await RenderingServer.frame_post_draw\n",
     b"# await RenderingServer.frame_post_draw\n",
     ["probe_code_waits_frame_post_draw",
      "probe_copy_matches_game_deployed"]),
    ("M26_probe_injects_apply", "tests/p4_live_probe.gd",
     b"\t\tvar rec := _state()",
     b'\t\tvar rec := _state()\n\t\tarena.layer_3d.apply("focus", 8)',
     ["probe_code_never_injects_apply",
      "probe_copy_matches_game_deployed"]),
    ("M27_probe_overrides_mapping", "tests/p4_live_probe.gd",
     b"\t\tvar rec := _state()",
     b'\t\tvar rec := _state()\n\t\tarena.motion_3d["mapping"]["leg_cap_deg"] = 3.0',
     ["probe_code_never_overrides_mapping",
      "probe_copy_matches_game_deployed"]),
    # ── verify 自身的判据常量 ──
    ("M28_phase_order_swapped", "verify_live_p4.py",
     b'PHASE_ORDER = ("discard", "select", "reveal", "resolve")',
     b'PHASE_ORDER = ("discard", "select", "resolve", "reveal")',
     ["both_phase_order_per_turn"]),
    ("M29_row_minimum_inflated", "verify_live_p4.py",
     b'len(payload[t]["rows"]) >= 50',
     b'len(payload[t]["rows"]) >= 500',
     ["both_rows_above_50"]),
    ("M30_sample_interval_tampered", "verify_live_p4.py",
     b'live["sample_s"] == 0.12', b'live["sample_s"] == 0.25',
     ["sample_interval_0_12"]),
    ("M31_process_count_tampered", "verify_live_p4.py",
     b"len(cases) == 2", b"len(cases) == 3",
     ["two_processes_both_rc0"]),
    ("M32_pose_summary_gate_flipped", "verify_live_p4.py",
     b'"PASS" in str(', b'"FAIL" in str(',
     ["all_checks_pose_probe_pass"]),
    ("M33_probe_not_watched_flipped", "verify_live_p4.py",
     b'"tests/p4_live_probe.gd" not in shabase["before"]',
     b'"scripts/arena.gd" not in shabase["before"]',
     ["probe_not_in_watched_files"]),
]

APPEND_CASES = [
    ("M19_board_png_tail_appended",
     "boards/P4实机-节奏时间线.png", b"MUTATION_TAIL",
     ["three_boards_sha_match_report"]),
]

SELFTEST = ("DNR_SELFTEST", "data/live_p4.json",
            b"ANCHOR_THAT_DOES_NOT_EXIST_9f8a7b", b"x",
            ["upstream_live_all_green"])


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(raw: bytes, blob: bytes) -> bytes:
    """探针/源码按文件行尾写变异体；JSON 的 needle 不含换行，无影响。"""
    if b"\r\n" in raw and b"\r\n" not in blob:
        return blob.replace(b"\n", b"\r\n")
    return blob


def guard_env() -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple[int, str, list, bool]:
    p = subprocess.run(
        [sys.executable, "-u", str(VERIFY)],
        cwd=str(HERE), env=guard_env(), capture_output=True,
        timeout=180)
    text = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
    broken = ("Traceback" in text or "SyntaxError" in text
              or "JSONDecodeError" in text)
    try:
        rep = json.loads((D / "verify_live_p4.json").read_text(
            encoding="utf-8"))
        failed = list(rep.get("failed", []))
    except Exception:
        failed, broken = [], True
    return p.returncode, text, failed, broken


def one_case(name: str, rel: str, needle: bytes | None,
             mutant: bytes, expect: list[str], append: bool = False) -> dict:
    path = HERE / rel
    original = path.read_bytes()
    row = {"name": name, "path": str(path), "expect": expect}
    if append:
        hits = 1
        changed = original + mutant
    else:
        n_needle = as_eol(original, needle)
        hits = original.count(n_needle)
        row["anchor_hits"] = hits
        if hits != 1:
            row.update({"status": "DID NOT RUN", "why": "anchor hits %d" % hits})
            return row
        changed = original.replace(n_needle, as_eol(original, mutant), 1)
    path.write_bytes(changed)
    rc, text, failed, broken = run_verify()
    path.write_bytes(original)
    restored = sha(path.read_bytes()) == sha(original)
    red = [e for e in expect if e in failed]
    if broken:
        status = "BROKEN"
    elif red:
        status = "CAUGHT"
    else:
        status = "MISSED"
    row.update({"status": status, "rc": rc, "red": red,
                "failed_count": len(failed), "restored": restored,
                "traceback": broken})
    return row


def main() -> int:
    selftest = "--selftest-dnr" in sys.argv
    if selftest:
        cases = [SELFTEST + (False,)]
    else:
        cases = [
            (n, rel, needle, mutant, expect, False)
            for n, rel, needle, mutant, expect in CASES] + [
            (n, rel, None, tail, expect, True)
            for n, rel, tail, expect in APPEND_CASES]
    rows = []
    for name, rel, needle, mutant, expect, append in cases:
        row = one_case(name, rel, needle, mutant, expect, append)
        rows.append(row)
        print("%-38s %-12s restore=%s red=%s" % (
            row["name"], row["status"], row.get("restored"),
            ",".join(row.get("red", [])) or "-"), flush=True)

    caught = sum(r["status"] == "CAUGHT" for r in rows)
    dnr = sum(r["status"] == "DID NOT RUN" for r in rows)
    broken = sum(r["status"] == "BROKEN" for r in rows)
    missed = sum(r["status"] == "MISSED" for r in rows)
    restored = sum(r.get("restored") is True for r in rows)

    # 干净重跑：还原后必须回到全绿
    rc, text, failed, bad = run_verify()
    clean_line = next((l for l in text.splitlines()
                       if l.startswith("LIVE_P4_VERIFY ")), "")
    clean_ok = ("ALL GREEN" in clean_line and not failed and not bad)
    clean_total = clean_line.split()[1].split("/")[1] if clean_line else "0"

    if selftest:
        effective = dnr == 1 and caught == 0 and clean_ok
        print("MUTATION_LIVE_P4 %d/%d CAUGHT / DNR %d / BROKEN %d / "
              "MISSED %d / RESTORE %d/%d / clean %s/%s" % (
                  caught, len(rows), dnr, broken, missed, restored,
                  len(rows), clean_line.split()[1].split("/")[0]
                  if clean_line else "0", clean_total))
        print("SELFTEST_DNR_EFFECTIVE" if effective
              else "SELFTEST_DNR_INEFFECTIVE")
        ok = effective
        out = D / "mutation_live_p4_dnr.json"
    else:
        ok = (caught == len(rows) and dnr == 0 and broken == 0
              and missed == 0 and restored == len(rows) and clean_ok)
        print("MUTATION_LIVE_P4 %d/%d CAUGHT / DNR %d / BROKEN %d / "
              "MISSED %d / RESTORE %d/%d / clean %s/%s %s" % (
                  caught, len(rows), dnr, broken, missed, restored,
                  len(rows), clean_line.split()[1].split("/")[0]
                  if clean_line else "0", clean_total,
                  "ALL GREEN" if clean_ok else "FAILED"))
        out = OUT
    payload = {"cases": len(rows), "caught": caught, "dnr": dnr,
               "broken": broken, "missed": missed, "restored": restored,
               "clean_ok": clean_ok, "clean_line": clean_line,
               "selftest": selftest, "ok": ok, "rows": rows}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
