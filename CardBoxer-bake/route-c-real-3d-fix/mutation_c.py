"""C 路线判据的变异验证：手工改坏 verify_c.py 会读的文件，确认判据真的报红。

纪律：
  - needle 必须是 ASCII bytes 字面量（中文值会 SyntaxError）；单行 needle 避开 CRLF 口径。
  - 锚点匹配次数 != 1 => DID NOT RUN，计入未证明，不算 CAUGHT，也不让脚本崩。
  - 还原用二进制读写 + sha256 比对；不用 read_text/write_text（会改换行）。
  - 变异期间不编辑被读文件；守卫子进程禁写字节码。
  - 最后 clean re-run 必须 18/18。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_c.py"
RESULT = HERE / "mutation_c_result.json"

CASES = [
    ("M1", "c_build.json", b'"covered": 64006,', b'"covered": 1000,',
     "C04_smooth_weight_coverage"),
    ("M2", "c_build.json", b'"p999_edge_tear_m": 0.01806,',
     b'"p999_edge_tear_m": 0.28048,', "C07_tear_improvement"),
    ("M3", "c_gif_stats.json", b'"duration_sum_ms": 840,',
     b'"duration_sum_ms": 780,', "C11_gif_duration_conservation"),
    # M4 单行值 "42.786" 在 all 与 arm_only 各出现一次，必须用带 png 名的
    # 多行 needle 才能唯一定位；行尾按目标文件实际 EOL 转换。
    ("M4", "gain_sweep.json",
     b'"png": "sweep-g2.0-jab07.png",\n      "max_delta_deg": 42.786,',
     b'"png": "sweep-g2.0-jab07.png",\n      "max_delta_deg": 10.0,',
     "C14_sweep_monotonic"),
    ("M5", "c_build.py", b'mod = final.modifiers.new("weights_from_voxel_proxy", "DATA_TRANSFER")',
     b'mod = final.modifiers.new("weights_from_voxel_proxy", "DATA_TRANSFER_X")',
     "C01_source_wiring"),
    ("M6", "gain_sweep.json", b'"usable_gain_range": "1.0 .. 1.5 (2.0 marginal)"',
     b'"usable_gain_range": "1.0 .. 3.0"', "C16_usable_gain_range_named"),
    ("M7", "gain_sweep_blender.json", b'"baseline_mapping_sha256": "',
     b'"baseline_mapping_sha256": "BROKEN', "C13_sweep_blender_shape"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(needle: bytes, data: bytes) -> bytes:
    """多行 needle 按目标文件实际行尾转换（本仓归档 JSON 是 CRLF）。"""
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    return needle.replace(b"\n", eol)


def guard_env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple[int, dict]:
    p = subprocess.run([PY, "-u", str(VERIFY)], cwd=str(HERE),
                       env=guard_env(), capture_output=True, text=True,
                       timeout=180)
    result = {}
    rp = HERE / "verify_c_result.json"
    if rp.is_file():
        result = json.loads(rp.read_text(encoding="utf-8"))
    return p.returncode, result


def main() -> int:
    selftest = os.environ.get("C_MUTATION_SELFTEST") == "1"
    cases = list(CASES)
    if selftest:
        # 故意让 M4 锚点失配，证明 DID NOT RUN 分支真的会计入未证明
        cases[3] = ("M4", "gain_sweep.json",
                    b'"png": "sweep-g9.9-jab07.png",\n      "max_delta_deg": 10.0,',
                    b'"png": "sweep-g9.9-jab07.png",\n      "max_delta_deg": 1.0,',
                    "C14_sweep_monotonic")

    out = []
    restored = 0
    for cid, rel, needle, mutant, target in cases:
        path = HERE / rel
        orig = path.read_bytes()
        orig_sha = sha(orig)
        n, m = as_eol(needle, orig), as_eol(mutant, orig)
        count = orig.count(n)
        if count != 1:
            out.append({"case": cid, "status": "DID NOT RUN",
                        "reason": f"anchor_count={count} in {rel}",
                        "target": target})
            print(f"[{cid}] DID NOT RUN anchor_count={count} in {rel}", flush=True)
            continue
        path.write_bytes(orig.replace(n, m, 1))
        try:
            rc, res = run_verify()
            failed = [c["name"] for c in res.get("checks", []) if not c["ok"]]
            caught = rc != 0 and target in failed
            out.append({"case": cid, "status": "CAUGHT" if caught else "ESCAPED",
                        "returncode": rc, "target": target,
                        "failed_checks": failed[:6]})
            print(f"[{cid}] {'CAUGHT' if caught else 'ESCAPED'} "
                  f"rc={rc} failed={failed[:4]}", flush=True)
        finally:
            path.write_bytes(orig)
            ok = sha(path.read_bytes()) == orig_sha
            restored += 1 if ok else 0
            out[-1]["restored_sha256_ok"] = ok
            if not ok:
                print(f"[{cid}] RESTORE FAILED {rel}", flush=True)

    rc, clean = run_verify()
    clean_ok = rc == 0 and clean.get("verified") is True
    caught = sum(1 for o in out if o["status"] == "CAUGHT")
    did_not_run = sum(1 for o in out if o["status"] == "DID NOT RUN")
    escaped = sum(1 for o in out if o["status"] == "ESCAPED")
    restore_ok = all(o.get("restored_sha256_ok", True) for o in out)

    summary = {
        "cases": out, "caught": caught, "total": len(cases),
        "did_not_run": did_not_run, "escaped": escaped,
        "restored": restored, "restore_all_ok": restore_ok,
        "clean_rerun": "GREEN" if clean_ok else "RED",
        "clean_passed": clean.get("passed"), "clean_total": clean.get("total"),
        "selftest": selftest,
        "verdict": ("MUTATION_C_OK" if caught == len(cases) and clean_ok
                    and restore_ok and did_not_run == 0 else "MUTATION_C_FAILED"),
    }
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"MUTATION_C {caught}/{len(cases)} CAUGHT "
          f"did_not_run={did_not_run} escaped={escaped} "
          f"restore={restored}/{len(cases)} clean={summary['clean_rerun']} "
          f"{summary['verdict']}", flush=True)
    return 0 if summary["verdict"] == "MUTATION_C_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
