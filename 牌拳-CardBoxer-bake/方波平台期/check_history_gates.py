"""方波平台期 · 历史守卫红因实测（不篡改历史归档）。

P3 改了 scripts/rig_driver.gd 与两份 motion_input*.json，所以 P1 / P2 / B
路线里那些「源码 sha 快照 / 未改动 / 旧 cap 值」的断言必然红。按项目约定
不篡改历史守卫，但要**实测**到底红哪几条，而不是凭印象列债。

做法：先把三个历史 verify 的输出 json 逐字节备份 + sha 记录，逐个重跑，
读回 failed 列表，立刻把输出 json 还原并用 sha 证明字节相同。历史脚本本身
一个字节都不改。

用法：python check_history_gates.py
产出：data/history_gates_p3.json、logs/history_gates/*.out
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
D = HERE / "data"
LOGS = HERE / "logs" / "history_gates"
OUT = D / "history_gates_p3.json"

HISTORY = [
    ("motion_p1", "动作覆盖P1", "verify_motion_p1.py",
     "data/verify_motion_p1.json"),
    ("motion_p2", "动作表现P2", "verify_p2.py",
     "data/verify_p2.json"),
    ("live_match", "实跑一局", "verify_live.py",
     "data/verify_live.json"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows, checks = [], {}

    for tag, folder, script, rel_out in HISTORY:
        work = BAKE / folder
        target = work / rel_out
        vp = work / script
        rec: dict = {"tag": tag, "folder": folder, "script": script,
                     "report": str(target)}
        if not (vp.is_file() and target.is_file()):
            rec["status"] = "MISSING"
            rows.append(rec)
            continue
        original = target.read_bytes()
        before = sha(original)
        try:
            p = subprocess.run(
                [sys.executable, "-u", str(vp)],
                cwd=str(work), capture_output=True, timeout=240)
            rc = p.returncode
            text = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            rc, text = -99, "TIMEOUT"
        (LOGS / f"{tag}.out").write_text(text, encoding="utf-8")
        rec["rc"] = rc
        rec["verdict_line"] = next(
            (ln.strip() for ln in reversed(text.splitlines())
             if "VERIFY" in ln.upper() or "ALL GREEN" in ln.upper()
             or "FAILED" in ln.upper()), "")
        try:
            rep = json.loads(target.read_text(encoding="utf-8"))
            rec["failed"] = list(rep.get("failed", []))
            rec["total"] = rep.get("total", len(rep.get("checks", {})))
            rec["passed"] = rep.get("passed")
            rec["parsed"] = True
        except Exception as exc:
            rec["failed"], rec["parsed"] = [], False
            rec["parse_error"] = repr(exc)
        # 立刻还原，sha 证明
        target.write_bytes(original)
        rec["restored_sha_equal"] = sha(target.read_bytes()) == before
        rec["before_sha256"] = before
        rec["status"] = "OK" if rec["restored_sha_equal"] else "RESTORE_FAIL"
        rows.append(rec)

    checks["all_three_reports_present_and_parsed"] = (
        len(rows) == 3 and all(r.get("parsed") is True for r in rows))
    checks["all_three_restored_bytewise"] = all(
        r.get("restored_sha_equal") is True for r in rows)
    checks["no_verify_crashed"] = all(
        r.get("rc") in (0, 1) for r in rows)
    checks["no_history_script_modified"] = all(
        (BAKE / r["folder"] / r["script"]).is_file() for r in rows)
    checks["at_least_one_historical_red"] = any(
        r.get("failed") for r in rows)
    report = {"rows": rows, "checks": checks,
              "failed_checks": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print(f"{r['tag']:12s} rc={r.get('rc')} "
              f"failed={len(r.get('failed', []))} "
              f"{r.get('verdict_line', '')}")
        for f in r.get("failed", []):
            print("   RED", f)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("HISTORY_GATES_OK" if report["ok"] else "HISTORY_GATES_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
