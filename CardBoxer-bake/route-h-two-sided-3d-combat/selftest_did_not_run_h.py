"""证明 mutation_h.py 的「锚点失配 = DID NOT RUN」分支真的有牙。

做法：复制一份变异脚本到 logs/（清单排除目录），把 M01 的 needle
改成一个盘上绝不会出现的字符串，用 H_ROOT 指回真工作区后跑它。
期望：M01 被标 DID NOT RUN、汇总 MUTATION_H_FAILED（不算通过）、
其余 12 组照常 CAUGHT 并逐字节还原、clean re-run 仍 GREEN。

用法：python selftest_did_not_run_h.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "mutation_h.py"
COPY = HERE / "logs" / "selftest_mutation_h.py"
NEEDLE = '"retired_metric":'
ABSENT = '"retired_metric_ABSENT999":'


def main() -> int:
    src = SRC.read_text(encoding="utf-8")
    anchor = src.find("CASES = [")
    assert anchor > 0, "CASES block not found"
    head, tail = src[:anchor], src[anchor:]
    assert NEEDLE in tail, "needle literal not in CASES"
    patched = head + tail.replace(NEEDLE, ABSENT, 1)
    assert ABSENT in patched and patched != src
    COPY.parent.mkdir(parents=True, exist_ok=True)
    COPY.write_text(patched, encoding="utf-8")

    env = os.environ.copy()
    env["H_ROOT"] = str(HERE)
    p = subprocess.run([sys.executable, "-u", str(COPY)],
                       capture_output=True, timeout=300, env=env)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    (HERE / "logs" / "selftest_did_not_run_h.out").write_text(
        out, encoding="utf-8")

    checks = {
        "m01_marked_did_not_run": "M01_retired_metric_renamed DID NOT RUN" in out,
        "dnr_counted": "DID_NOT_RUN=1" in out,
        "not_reported_as_ok": "MUTATION_H_FAILED" in out,
        "other_cases_still_caught": "CAUGHT=12/13" in out,
        "all_mutations_restored": "restore=12/12" in out,
        "clean_rerun_green": "clean=GREEN" in out,
        "copy_script_left_in_excluded_dir": COPY.is_file(),
    }
    COPY.unlink(missing_ok=True)
    checks["temp_script_removed"] = not COPY.exists()
    for k, v in checks.items():
        print(("OK   " if v else "FAIL ") + k)
    ok = all(checks.values())
    print(f"SELFTEST_H {sum(checks.values())}/{len(checks)}")
    print("DID_NOT_RUN_BRANCH_OK" if ok else "DID_NOT_RUN_BRANCH_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
