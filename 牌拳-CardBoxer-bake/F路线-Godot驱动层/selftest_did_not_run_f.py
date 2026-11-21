"""失配自检：故意让一个变异锚点不存在，证明 DID NOT RUN 分支有牙。

这是变异 harness 自身的承重判据：如果锚点失配被静默当成 CAUGHT，
整个变异验证就是假的（本机踩过：CRLF + indent=2 让单行 needle 匹配 0 次，
脚本却照样打印 4/4）。

断言：
  · mutation_f.py --selftest 退出码 0（自检本身跑完）
  · 结果里 did_not_run == 1
  · 整体验收 ok == false（失配计入未证明）
  · 其余 case 仍照跑、clean re-run 仍 GREEN
用法：python selftest_did_not_run_f.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = HERE / "logs" / "mutation_f_selftest_result.json"
OUT = HERE / "logs" / "selftest_did_not_run_f.json"


def main() -> int:
    r = subprocess.run([sys.executable, str(HERE / "mutation_f.py"),
                        "--selftest"],
                       cwd=str(HERE), capture_output=True, text=True,
                       timeout=600)
    text = (r.stdout or "") + (r.stderr or "")
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    checks = {
        "selftest_exit_0": r.returncode == 0,
        "marker_printed": "SELFTEST_ASSERTION_OK" in text,
        "did_not_run_one": data["did_not_run"] == 1,
        "overall_not_proven": data["ok"] is False,
        "other_cases_still_ran": len(data["results"]) == data["cases"],
        "clean_rerun_green": data["clean_rerun_green"] is True,
        "runtime_clean_green": data["runtime_clean_green"] is True,
        "negative_control_ok": data["negative_control_ok"] is True,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({"checks": checks, "ok": ok,
                               "stdout_tail": text.strip().splitlines()[-6:]},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"SELFTEST_DID_NOT_RUN {sum(checks.values())}/{len(checks)}")
    print("DID_NOT_RUN_BRANCH_OK" if ok else "DID_NOT_RUN_BRANCH_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
