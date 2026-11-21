"""证明 mutation_i.py 的「锚点失配 = DID NOT RUN」分支真的有牙。

做法：复制一份变异脚本到 logs/（清单排除目录），把 M01 的 needle
改成盘上绝不会出现的字符串，用 I_ROOT 指回真工作区后跑它。
期望：M01 被标 DID NOT RUN、汇总 MUTATION_I_FAILED（不算通过）、
其余 11 组照常按点名判据 CAUGHT 并逐字节还原、clean re-run 仍 GREEN。

用法：python selftest_did_not_run_i.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "mutation_i.py"
COPY = HERE / "logs" / "selftest_mutation_i.py"
NEEDLE = b"const FOE_DRAW_SCALE_X := 1.22"
ABSENT = b"const FOE_DRAW_SCALE_X := 9.99_ABSENT"
TOTAL = 12


def main() -> int:
    src = SRC.read_text(encoding="utf-8")
    anchor = src.find("CASES = [")
    assert anchor > 0, "CASES block not found"
    head, tail = src[:anchor], src[anchor:]
    assert NEEDLE.decode() in tail, "needle literal not in CASES"
    patched = head + tail.replace(NEEDLE.decode(), ABSENT.decode(), 1)
    assert ABSENT.decode() in patched and patched != src
    COPY.parent.mkdir(parents=True, exist_ok=True)
    COPY.write_text(patched, encoding="utf-8")

    env = os.environ.copy()
    env["I_ROOT"] = str(HERE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, "-u", str(COPY)],
                       capture_output=True, timeout=300, env=env)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    # 不要与 shell 重定向的 selftest_did_not_run_i.out 同名，否则
    # 子进程输出会把本脚本自己的判据输出覆盖成一份混在一起的日志。
    (HERE / "logs" / "selftest_mutation_i_child.out").write_text(
        out, encoding="utf-8")

    checks = {
        "m01_marked_did_not_run": (
            "M01_source_scale_reverted DID NOT RUN" in out),
        "dnr_counted": "DID_NOT_RUN=1" in out,
        "not_reported_as_ok": "MUTATION_I_FAILED" in out,
        "other_cases_still_caught": f"CAUGHT={TOTAL - 1}/{TOTAL}" in out,
        "all_mutations_restored": (
            f"restore={TOTAL - 1}/{TOTAL - 1}" in out),
        "clean_rerun_green": "clean=GREEN" in out,
        "copy_script_left_in_excluded_dir": COPY.is_file(),
    }
    COPY.unlink(missing_ok=True)
    checks["temp_script_removed"] = not COPY.exists()
    for k, v in checks.items():
        print(("OK   " if v else "FAIL ") + k)
    ok = all(checks.values())
    print(f"SELFTEST_I {sum(checks.values())}/{len(checks)}")
    print("DID_NOT_RUN_BRANCH_OK" if ok else "DID_NOT_RUN_BRANCH_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
