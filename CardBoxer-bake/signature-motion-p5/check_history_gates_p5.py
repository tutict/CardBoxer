# -*- coding: utf-8 -*-
"""P5 · 历史守卫红因实测（#218：列债，不篡改历史归档）。

P5 改了三份动作表，历轮 verify 里钉着旧表 sha / 旧数值 / 旧报告文本，
必然有红。按项目约定**不改历史脚本与历史结论**，只逐个重跑、读回红因、
逐字节还原报告，并把「P5 之前就红」与「P5 新增红」分开：
  * P4 的 history_gates_p4_after.json 就是 P5 落地前的实测基线；
  * 新增的三份 verify 没有 before 基线，标 no_baseline 并如实列红因。

用法：python check_history_gates_p5.py
产出：data/history_gates_p5.json、logs/history_gates_p5/<tag>.out
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
DATA = HERE / "data"
LOGDIR = HERE / "logs" / "history_gates_p5"
OUT = DATA / "history_gates_p5.json"
P4_BASELINE = BAKE / "native-plateau-p4" / "data" / "history_gates_p4_after.json"
# 历史 verify 有 PIL 依赖；P4 实测过必须用这个 venv，否则 import 阶段崩栈
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
    ("native_p4", "native-plateau-p4", "verify_native.py",
     "data/verify_native.json"),
    ("live_p4", "live-acceptance-p4", "verify_live_p4.py",
     "data/verify_live_p4.json"),
    ("pose_spec_p5", "signature-motion-p5", "verify_pose_spec.py",
     "verify_pose_spec_result.json"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    before_failed = {}
    if P4_BASELINE.is_file():
        for r in json.loads(P4_BASELINE.read_text(
                encoding="utf-8-sig")).get("rows", []):
            before_failed[r["tag"]] = set(r.get("failed", []))

    rows = []
    for tag, folder, script, rel_out in HISTORY:
        work = BAKE / folder
        vp, target = work / script, work / rel_out
        rec = {"tag": tag, "folder": folder, "script": script,
               "report": str(target)}
        if not (vp.is_file() and target.is_file() and VENV_PY.is_file()):
            rec["status"] = "MISSING"
            rows.append(rec)
            continue
        original = target.read_bytes()
        before = sha(original)
        script_before = sha(vp.read_bytes())
        try:
            p = subprocess.run(
                [str(VENV_PY), "-B", "-u", str(vp)],
                cwd=str(work), capture_output=True, timeout=300)
            rc, text = p.returncode, (p.stdout + b"\n" + p.stderr).decode(
                "utf-8", "replace")
        except subprocess.TimeoutExpired:
            rc, text = -99, "TIMEOUT"
        (LOGDIR / f"{tag}.out").write_text(text, encoding="utf-8")
        rec["rc"] = rc
        rec["traceback"] = "Traceback (most recent call last):" in text
        rec["verdict_line"] = next(
            (ln.strip() for ln in reversed(text.splitlines())
             if "VERIFY" in ln.upper() or "ALL GREEN" in ln.upper()
             or "FAILED" in ln.upper()), "")
        try:
            rep = json.loads(target.read_text(encoding="utf-8-sig"))
            # 历史报告有三种形状：顶层 failed 列表 / checks 字典 /
            # checks 列表（每项带 name+ok）。只认第一种会漏报成「零红因」。
            failed = list(rep.get("failed", []))
            ck = rep.get("checks")
            if not failed and isinstance(ck, dict):
                failed = [k for k, v in ck.items() if v is not True]
            elif not failed and isinstance(ck, list):
                failed = [str(c.get("name", c)) for c in ck
                          if c.get("ok") is not True]
            rec["failed"] = failed
            rec["total"] = rep.get("total", len(failed) + sum(
                1 for v in (ck.values() if isinstance(ck, dict)
                            else [c.get("ok") for c in ck]
                            if isinstance(ck, list) else [])
                if v is True))
            rec["passed"] = rep.get("passed")
            rec["parsed"] = True
        except Exception as exc:
            rec.update({"failed": [], "parsed": False,
                        "parse_error": repr(exc)})
        target.write_bytes(original)
        rec["restored_sha_equal"] = sha(target.read_bytes()) == before
        rec["script_sha_unchanged"] = sha(vp.read_bytes()) == script_before
        rec["before_sha256"] = before
        rec["baseline"] = ("p4_after" if tag in before_failed
                           else "no_baseline")
        rec["new_reds_vs_baseline"] = sorted(
            set(rec["failed"]) - before_failed[tag]) \
            if tag in before_failed else []
        rec["status"] = ("OK" if rec["restored_sha_equal"]
                         and rec["script_sha_unchanged"]
                         else "RESTORE_FAIL")
        rows.append(rec)

    checks = {
        "all_reports_present_and_parsed": (
            len(rows) == len(HISTORY)
            and all(r.get("parsed") is True for r in rows)),
        "all_restored_bytewise": all(
            r.get("restored_sha_equal") is True for r in rows),
        "no_history_script_modified": all(
            r.get("script_sha_unchanged") is True for r in rows),
        "no_verify_crashed": all(
            r.get("rc") in (0, 1) and r.get("traceback") is False
            for r in rows),
        "all_verdict_lines_present": all(
            bool(r.get("verdict_line"))
            and not r["verdict_line"].startswith("File ")
            for r in rows),
        "venv_python_has_pil": VENV_PY.is_file(),
        "p4_baseline_used": bool(before_failed),
    }
    report = {
        "purpose": "measure, list and own historical red causes; never edit them",
        "baseline_source": str(P4_BASELINE),
        "rows": rows,
        "checks": checks,
        "failed_checks": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print("%-14s rc=%-3s failed=%-3d baseline=%-12s %s" % (
            r["tag"], r.get("rc"), len(r.get("failed", [])),
            r.get("baseline", "?"), r.get("verdict_line", "")))
        for f in r.get("failed", []):
            print("   RED", f)
        if r.get("new_reds_vs_baseline"):
            print("   NEW_RED", r["new_reds_vs_baseline"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("HISTORY_GATES_P5_OK" if report["ok"]
          else "HISTORY_GATES_P5_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
