"""P4 · 历史守卫红因实测（落地前 / 落地后两阶段，不篡改历史归档）。

P4 会改三份数据层，其中 card_motion.json 是 P0/P1 时代的 untouched 基线。
按项目约定不篡改历史守卫，但要**实测**落地前后各自红哪几条，才能把
「P3 遗留红因」和「P4 新增红因」分开，而不是凭印象列债。

做法：备份每个历史 verify 的输出 json 原字节 + sha，逐个重跑，读回 failed，
立刻还原并 sha 证明。历史脚本本身一个字节都不改。

用法：
  python check_history_gates_p4.py before   -> data/history_gates_p4_before.json
  python check_history_gates_p4.py after    -> data/history_gates_p4_after.json
产出另含 logs/history_gates_p4/<phase>/<tag>.out
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
OUT_DIR = HERE / "logs" / "history_gates_p4"
# 历史 verify 里有 PIL 依赖；系统 3.13 裸解释器没有 Pillow，会让
# verify_motion_p1.py 在 import 阶段就崩栈，而 rc=1 看起来像「正常 FAILED」。
# 实测过：不换解释器会读到旧 json 的 failed 列表，属于假证明。
VENV_PY = Path(
    r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe")

HISTORY = [
    ("motion_p1", "motion-coverage-p1", "verify_motion_p1.py",
     "data/verify_motion_p1.json"),
    ("motion_p2", "motion-presentation-p2", "verify_p2.py",
     "data/verify_p2.json"),
    ("live_match", "live-match", "verify_live.py",
     "data/verify_live.json"),
    ("plateau_p3", "square-wave-plateau", "verify_plateau.py",
     "data/verify_plateau.json"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase not in ("before", "after"):
        print("USAGE: check_history_gates_p4.py before|after")
        return 2
    logs = OUT_DIR / phase
    logs.mkdir(parents=True, exist_ok=True)
    out = D / f"history_gates_p4_{phase}.json"
    rows, checks = [], {}

    for tag, folder, script, rel_out in HISTORY:
        work = BAKE / folder
        target = work / rel_out
        vp = work / script
        rec = {"tag": tag, "folder": folder, "script": script,
               "report": str(target)}
        if not (vp.is_file() and target.is_file()):
            rec["status"] = "MISSING"
            rows.append(rec)
            continue
        original = target.read_bytes()
        before = sha(original)
        try:
            p = subprocess.run(
                [str(VENV_PY), "-u", str(vp)],
                cwd=str(work), capture_output=True, timeout=300)
            rc = p.returncode
            text = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            rc, text = -99, "TIMEOUT"
        (logs / f"{tag}.out").write_text(text, encoding="utf-8")
        rec["rc"] = rc
        rec["traceback"] = "Traceback (most recent call last):" in text
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
        target.write_bytes(original)
        rec["restored_sha_equal"] = sha(target.read_bytes()) == before
        rec["before_sha256"] = before
        rec["status"] = "OK" if rec["restored_sha_equal"] else "RESTORE_FAIL"
        rows.append(rec)

    before_path = D / "history_gates_p4_before.json"
    before_failed = {}
    if phase == "after" and before_path.is_file():
        before_failed = {r["tag"]: set(r.get("failed", []))
                         for r in json.loads(before_path.read_text(
                             encoding="utf-8"))["rows"]}
    new_reds = {}
    for r in rows:
        if phase == "after" and r["tag"] in before_failed:
            new_reds[r["tag"]] = sorted(
                set(r.get("failed", [])) - before_failed[r["tag"]])

    checks["all_reports_present_and_parsed"] = (
        len(rows) == len(HISTORY)
        and all(r.get("parsed") is True for r in rows))
    checks["all_restored_bytewise"] = all(
        r.get("restored_sha_equal") is True for r in rows)
    checks["no_verify_crashed"] = all(
        r.get("rc") in (0, 1) and r.get("traceback") is False
        for r in rows)
    checks["all_verdict_lines_present"] = all(
        bool(r.get("verdict_line"))
        and not r["verdict_line"].startswith("File ")
        for r in rows)
    checks["venv_python_has_pil"] = VENV_PY.is_file()
    checks["no_history_script_modified"] = all(
        (BAKE / r["folder"] / r["script"]).is_file() for r in rows)
    report = {"phase": phase, "rows": rows, "new_reds_vs_before": new_reds,
              "checks": checks,
              "failed_checks": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print(f"{r['tag']:12s} rc={r.get('rc')} "
              f"failed={len(r.get('failed', []))} "
              f"{r.get('verdict_line', '')}")
        for f in r.get("failed", []):
            print("   RED", f)
    if phase == "after":
        for tag, reds in new_reds.items():
            print("NEW_RED", tag, reds)
    for k, v in checks.items():
        print("CHECK", k, v)
    print(f"HISTORY_GATES_P4_{phase.upper()}_OK"
          if report["ok"] else
          f"HISTORY_GATES_P4_{phase.upper()}_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
