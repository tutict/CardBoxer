"""G 路线：证明 mutation_g.py 的「锚点失配 = 未证明」分支真的有牙。

做法：把 mutation_g.py 复制到**工作区外**（%TEMP%），三处改写：
  ① HERE 固定指向真实工作区（副本不在工作区，__file__ 会指错）；
  ② 结果文件改名，不覆盖主变异证据；
  ③ 把 M10 的 needle 改成一个不存在的字面量。
然后跑**正常模式**（不带 --selftest），期望：
  · 该 case 报 DID NOT RUN 且 reason 是 anchor_count=0
  · 其余 case 仍有 CAUGHT（不是整批崩掉）
  · unproven_positive > 0、ok=False、退出码非 0
  · clean re-run GREEN、还原全部成功
副本放在工作区外，避免「清单覆盖全部文件」判据在守卫运行期间
看到临时文件而连锁报红，把 clean re-run 弄成假红。

用法：python selftest_did_not_run_g.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
SRC = HERE / "mutation_g.py"
OUT = HERE / "logs" / "selftest_did_not_run_g.json"
NEGATIVE_RESULT = HERE / "logs" / "mutation_g_selftest_negative.json"
NEGATIVE_LOG = HERE / "logs" / "run_selftest_did_not_run_g.out"


def main() -> int:
    assert SRC.is_file(), SRC
    text = SRC.read_text(encoding="utf-8")
    a = "HERE = Path(__file__).resolve().parent"
    b = f'HERE = Path(r"{HERE}")'
    assert text.count(a) == 1, f"HERE anchor: {text.count(a)}"
    text = text.replace(a, b, 1)
    a2 = 'OUT_MAIN = LOGS / "mutation_g_result.json"'
    b2 = 'OUT_MAIN = LOGS / "mutation_g_selftest_negative.json"'
    assert text.count(a2) == 1, f"OUT anchor: {text.count(a2)}"
    text = text.replace(a2, b2, 1)
    a3 = 'b"const DEFAULT_SIDE_YAW := 55.0"'
    b3 = 'b"const DEFAULT_SIDE_YAW := 999.0_NO_SUCH"'
    assert text.count(a3) == 1, f"needle anchor: {text.count(a3)}"
    text = text.replace(a3, b3, 1)

    tmp = Path(tempfile.mkdtemp(prefix="fa-g-selftest-"))
    script = tmp / "mutation_g_negative.py"
    script.write_bytes(text.encode("utf-8"))
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if NEGATIVE_RESULT.is_file():
        NEGATIVE_RESULT.unlink()
    p = subprocess.run([PY, str(script)], cwd=str(HERE), env=env,
                       capture_output=True, timeout=300)
    out = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode(
        "utf-8", "replace")
    NEGATIVE_LOG.write_text(out, encoding="utf-8")

    d = json.loads(NEGATIVE_RESULT.read_text(encoding="utf-8")) \
        if NEGATIVE_RESULT.is_file() else {}
    dnr = [r for r in d.get("cases", []) if r.get("status") == "DID NOT RUN"]
    caught = [r for r in d.get("cases", []) if r.get("status") == "CAUGHT"]
    checks = {
        "exit_nonzero": p.returncode != 0,
        "not_selftest_mode": d.get("selftest") is False,
        "has_did_not_run": len(dnr) == 1,
        "dnr_is_m10": any(r.get("id") == "M10" for r in dnr),
        "dnr_reason_anchor": any("anchor_count=0" in r.get("reason", "")
                                 for r in dnr),
        "other_cases_still_caught": len(caught) >= 10,
        "did_not_run_counted_unproven": d.get("unproven_positive", 0) >= 1,
        "overall_not_ok": d.get("ok") is False,
        "clean_rerun_green": d.get("clean_rerun") == "GREEN",
        "restore_all_ok": d.get("restore_ok") == d.get("restore_total")
                          and d.get("restore_total", 0) > 0,
        "output_marker": "MUTATION_G_FAILED" in out,
    }
    failed = [k for k, v in checks.items() if not v]
    ok = not failed
    OUT.write_text(json.dumps({
        "checks": checks, "failed": failed,
        "did_not_run": len(dnr), "caught": len(caught),
        "unproven_positive": d.get("unproven_positive"),
        "clean_rerun": d.get("clean_rerun"),
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k in failed:
        print("  FAIL", k)
    print(f"SELFTEST {len(checks) - len(failed)}/{len(checks)} "
          f"dnr={len(dnr)} caught={len(caught)}")
    print("DID_NOT_RUN_BRANCH_OK" if ok else "DID_NOT_RUN_BRANCH_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
