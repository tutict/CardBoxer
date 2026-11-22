"""verify_a.py 的变异验证：改坏盘上产物，确认被点名的判据真的报红。

纪律（沿用本仓既有 harness）：
  · needle / mutant 只用 ASCII bytes；中文值不进 needle；
  · 锚点 count != 1 一律记 DID NOT RUN 并计入未证明，绝不静默跳过；
  · 逐字节还原 + sha256 比对，不用文本模式读写（换行会被转换）；
  · 每组要求「指定判据红」且「哨兵判据仍绿」，防止一个文件坏掉全表皆红；
  · 收尾 clean re-run 必须 26/26 全绿。
  · A_MUTATION_SELFTEST=1 故意让 M1 锚点失配，验证失配分支有牙。
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
VERIFY = HERE / "verify_a.py"
RESULT = HERE / "verify_a_result.json"

ZERO = b"0" * 64

CASES = [
    {"id": "M1", "file": "baseline.json",
     "needle": b'"sha256": "76004e212759c76f8f84a5d8fbab58680eedc4ebcd11d663e783f8c234e13165"',
     "mutant": b'"sha256": "' + ZERO + b'"',
     "red": ["A-01_baseline_inputs_intact"],
     "sentinel": "A-13_frame_shape"},
    {"id": "M2", "file": "baseline.json",
     "needle": b'"sha256": "ae5ab3382f0a6da19b3882b9bd403c22c19da6b2e9b43f50c49c49f5d2d46145"',
     "mutant": b'"sha256": "' + ZERO + b'"',
     "red": ["A-02_game_source_unchanged"],
     "sentinel": "A-01_baseline_inputs_intact"},
    {"id": "M3", "file": "bake_probe.json",
     "needle": b'"bake_ok": true', "mutant": b'"bake_ok": false',
     "red": ["A-06_bake_probe_nonblank"],
     "sentinel": "A-07_a1_is_not_texture_transfer"},
    {"id": "M4", "file": "surfdeform_probe.json",
     "needle": b'"rest_drift_m": 1.92e-06', "mutant": b'"rest_drift_m": 0.5',
     "red": ["A-08_surfdeform_probe_bind"],
     "sentinel": "A-09_probe_assets_preserved"},
    {"id": "M5", "file": "a_build.json",
     "needle": b'"reopen_drive_max_displacement_m": 0.81099',
     "mutant": b'"reopen_drive_max_displacement_m": 0.0',
     "red": ["A-12_reopen_is_driveable"],
     "sentinel": "A-13_frame_shape"},
    {"id": "M6", "file": "metrics_a.json",
     "needle": b'"reach_mean_A2x15_over_A2x1": 1.4514',
     "mutant": b'"reach_mean_A2x15_over_A2x1": 1.0000',
     "red": ["A-17_gain_ratio_double_computed"],
     "sentinel": "A-18_tear_improved_over_v2"},
    {"id": "M7", "file": "metrics_a.json",
     "needle": b'"tear_wins_frames": 65', "mutant": b'"tear_wins_frames": 0',
     "red": ["A-19_ab_counts_double_computed"],
     "sentinel": "A-17_gain_ratio_double_computed"},
    {"id": "M8", "file": "a_build.py",
     "needle": b"ARM_GAIN = 1.5", "mutant": b"ARM_GAIN = 1.0",
     "red": ["A-23_params_match_source"],
     "sentinel": "A-24_source_wiring"},
    {"id": "M9", "file": "a_build.py",
     "needle": b'src.modifiers.new("follow_continuous_shell", "SURFACE_DEFORM")',
     "mutant": b'src.modifiers.new("follow_continuous_shell", "ARMATURE")',
     "red": ["A-24_source_wiring"],
     "sentinel": "A-23_params_match_source"},
    {"id": "M10", "file": "a_build.json",
     "needle": b'"sha256": "d5384c803194af0404b87960559efb82d129fb7a3b297aa00c0b03edf6a8cfbd"',
     "mutant": b'"sha256": "' + ZERO + b'"',
     "red": ["A-21_shot_files_intact"],
     "sentinel": "A-22_boards_nonblank"},
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
    selftest = os.environ.get("A_MUTATION_SELFTEST") == "1"
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
            # 按「用例」计数，不能按文件名字典：多个用例改同一文件会被合并。
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
    (HERE / ("mutation_a_selftest_result.json" if selftest
             else "mutation_a_result.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TOTAL={len(cases)} CAUGHT={caught} DID_NOT_RUN={dnr} "
          f"RESTORE={restore_ok}/{len(cases)-dnr} CLEAN={clean_green}")
    print("MUTATION_A_OK" if ok else "MUTATION_A_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
