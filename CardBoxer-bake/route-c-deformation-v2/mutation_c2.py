"""verify_c2.py 的变异验证：改坏盘上产物，确认被点名的判据真的报红。

纪律（沿用本仓既有 harness）：
  · needle / mutant 只用 ASCII bytes；中文值不进 needle；
  · 锚点 count != 1 一律记 DID NOT RUN 并计入未证明，绝不静默跳过；
  · 逐字节还原 + sha256 比对，不用文本模式读写（换行会被转换）；
  · 每组要求「指定判据红」且「哨兵判据仍绿」，防止一个文件坏掉全表皆红；
  · 收尾 clean re-run 必须 22/22 全绿。
  · C2_MUTATION_SELFTEST=1 故意让 M1 锚点失配，验证失配分支有牙。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
VERIFY = HERE / "verify_c2.py"
RESULT = HERE / "verify_c2_result.json"

CASES = [
    {"id": "M1", "file": "baseline.json",
     "needle": b'"sha256": "76004e212759c76f8f84a5d8fbab58680eedc4ebcd11d663e783f8c234e13165"',
     "mutant": b'"sha256": "0000000000000000000000000000000000000000000000000000000000000000"',
     "red": ["V2-01_baseline_inputs_intact"],
     "sentinel": "V2-06_reach_ratio_double_computed"},
    {"id": "M2", "file": "metrics_summary.json",
     "needle": b'"gain_only_on_V1": 1.4515',
     "mutant": b'"gain_only_on_V1": 1.0000',
     "red": ["V2-06_reach_ratio_double_computed"],
     "sentinel": "V2-01_baseline_inputs_intact"},
    {"id": "M3", "file": "metrics_summary.json",
     "needle": b'"reach_non_negative_frames": 72',
     "mutant": b'"reach_non_negative_frames": 0',
     "red": ["V2-07_reach_non_negative_every_frame"],
     "sentinel": "V2-06_reach_ratio_double_computed"},
    {"id": "M4", "file": "c2_build.json",
     "needle": b'"max_vertex_delta_m": 6.43e-07',
     "mutant": b'"max_vertex_delta_m": 0.5',
     "red": ["V2-04_stance_identity"],
     "sentinel": "V2-05_frame_count_and_variants"},
    {"id": "M5", "file": "shells_probe.json",
     "needle": b'"vert_pct": 0.9346',
     "mutant": b'"vert_pct": 0.0500',
     "red": ["V2-16_shells_small_holds_body"],
     "sentinel": "V2-17_smooth_sweep_no_real_improvement"},
    {"id": "M6", "file": "smooth_sweep.json",
     "needle": b'"tear_gain_mean": 0.03453',
     "mutant": b'"tear_gain_mean": 0.00100',
     "red": ["V2-17_smooth_sweep_no_real_improvement"],
     "sentinel": "V2-16_shells_small_holds_body"},
    {"id": "M7", "file": "c2_build.json",
     "needle": b'"bytes": 410738',
     "mutant": b'"bytes": 1',
     "red": ["V2-19_final_shots_single_variable"],
     "sentinel": "V2-20_boards_nonblank"},
    {"id": "M8", "file": "c2_build.py",
     "needle": b"ARM_GAIN = 1.5",
     "mutant": b"ARM_GAIN = 1.0",
     "red": ["V2-21_params_match_source"],
     "sentinel": "V2-22_source_wiring"},
    {"id": "M9", "file": "c2_build.py",
     "needle": b'row["V2_final"] = row.pop("V2_gain")',
     "mutant": b'row["V2_final"] = row.get("V2_gain")',
     "red": ["V2-22_source_wiring"],
     "sentinel": "V2-21_params_match_source"},
]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(data: bytes, needle: bytes) -> bytes:
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    return needle.replace(b"\n", eol)


def run_verify():
    subprocess.run([PY, "-u", str(VERIFY)], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=180)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def main() -> int:
    selftest = os.environ.get("C2_MUTATION_SELFTEST") == "1"
    cases = [dict(c) for c in CASES]
    if selftest:
        cases[0]["needle"] = b'"sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"'

    rows = []
    restore = {}
    restore_ok = 0
    for case in cases:
        p = HERE / case["file"]
        orig = p.read_bytes()
        needle = as_eol(orig, case["needle"])
        mutant = as_eol(orig, case["mutant"])
        count = orig.count(needle)
        if count != 1:
            rows.append({"id": case["id"], "status": "DID NOT RUN",
                         "reason": f"anchor count={count} (need 1)",
                         "label": case["id"]})
            print(f"{case['id']} DID NOT RUN anchor count={count}")
            continue
        mutated = orig.replace(needle, mutant, 1)
        try:
            p.write_bytes(mutated)
            res = run_verify()
        finally:
            p.write_bytes(orig)
            # 按「用例」计数，不能按文件名字典：多个用例改同一文件会被合并，
            # 9 个用例只留 6 个 key，汇总会假报 RESTORE=6/9。
            ok_restore = sha256(p.read_bytes()) == sha256(orig)
            restore[case["file"]] = ok_restore
            restore_ok += int(ok_restore)
        red = [c["name"] for c in res["checks"] if not c["ok"]]
        green = [c["name"] for c in res["checks"] if c["ok"]]
        caught = all(n in red for n in case["red"]) and case["sentinel"] in green
        rows.append({"id": case["id"], "status": "CAUGHT" if caught else "MISSED",
                     "red": red, "sentinel_green": case["sentinel"] in green,
                     "restored": restore[case["file"]]})
        print(f"{case['id']} {'CAUGHT' if caught else 'MISSED'} "
              f"red={red} restored={restore[case['file']]}")

    clean = run_verify()
    clean_green = clean["passed"] == clean["total"]
    caught = sum(r["status"] == "CAUGHT" for r in rows)
    dnr = sum(r["status"] == "DID NOT RUN" for r in rows)
    all_restored = restore_ok == (len(cases) - dnr) and all(restore.values())
    ok = (caught == len(cases) and dnr == 0 and all_restored and clean_green)
    out = {"selftest": selftest, "total": len(cases), "caught": caught,
           "did_not_run": dnr, "restore": restore,
           "restore_all_ok": all_restored,
           "clean_rerun": {"passed": clean["passed"], "total": clean["total"],
                           "green": clean_green},
           "all_proven": ok, "rows": rows}
    (HERE / ("mutation_c2_selftest_result.json" if selftest
             else "mutation_c2_result.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TOTAL={len(cases)} CAUGHT={caught} DID_NOT_RUN={dnr} "
          f"RESTORE={restore_ok}/{len(cases)-dnr} CLEAN={clean_green}")
    print("MUTATION_C2_OK" if ok else "MUTATION_C2_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
