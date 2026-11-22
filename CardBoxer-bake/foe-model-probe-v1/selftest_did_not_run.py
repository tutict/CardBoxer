"""变异 harness 自身的承重验证：锚点失配必须报 DID NOT RUN 且整轮判 FAILED。

背景：首次 M4 用单行 needle 去匹配 indent=2 + CRLF 的 stats JSON，
匹配 0 次直接 assert 崩在半路，clean re-run 没跑、盘上 verify 结论停在
M3 变异中间态（9/10 FAIL）。修完锚点后，还顺手把「未证明计入汇总」写成
显式分支 —— 本脚本就是删掉它声称要防的那段，看会不会红。

纪律：对被测脚本做二进制变异、sha256 逐字节还原，不靠文本读写。
跑完必须重跑真 mutation_concept.py，把 log / result / verify 结论恢复成 clean 态。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "mutation_concept.py"
RESULT = HERE / "mutation_concept_result.json"
LOG = HERE / "selftest_did_not_run.log"

NEEDLE = b'"old": b"    174,"'      # M4 的真实锚点
BROKEN = b'"old": b"    999,"'      # 故意失配的锚点（stats 里没有 999）


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


original = TARGET.read_bytes()
original_sha = sha(original)
assert original.count(NEEDLE) == 1, "selftest 锚点不唯一，本自检没跑"
lines = []
try:
    TARGET.write_bytes(original.replace(NEEDLE, BROKEN, 1))
    assert sha(TARGET.read_bytes()) != original_sha, "selftest 变异没改变字节"
    p = subprocess.run([sys.executable, "-u", str(TARGET)],
                       capture_output=True, text=True)
    out = p.stdout
    res = json.loads(RESULT.read_text(encoding="utf-8"))
    checks = [
        ("selftest_process_exits_nonzero", p.returncode != 0),
        ("m4_reports_did_not_run", "M4 DID NOT RUN" in out),
        ("did_not_run_counted_in_summary", "did_not_run=1" in out),
        ("whole_run_failed_not_fake_green", "MUTATION_CONCEPT_FAILED" in out
            and res["verdict"] == "MUTATION_CONCEPT_FAILED"),
        ("m4_flagged_in_result_json", res["cases"][3]["did_not_run"] is True
            and res["cases"][3]["caught"] is False),
        ("other_cases_still_reported", all(f"M{i} CAUGHT" in out for i in (1, 2, 3))),
        ("clean_rerun_still_executed", "clean_rerun=GREEN" in out),
        ("all_targets_still_restored", "restore=4/4" in out),
    ]
    for name, ok in checks:
        lines.append(f"{'PASS' if ok else 'FAIL'}  {name}")
    lines.append("")
    lines.append(out.strip())
    passed = sum(1 for _, ok in checks if ok)
    verdict = "SELFTEST_DID_NOT_RUN_OK" if passed == len(checks) else "SELFTEST_FAILED"
    lines.append(f"\n{passed}/{len(checks)} PASS  {verdict}")
finally:
    TARGET.write_bytes(original)
restored = sha(TARGET.read_bytes()) == original_sha
lines.append(f"restore_sha256={restored}  {original_sha}")
LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
raise SystemExit(0 if verdict == "SELFTEST_DID_NOT_RUN_OK" and restored else 1)
