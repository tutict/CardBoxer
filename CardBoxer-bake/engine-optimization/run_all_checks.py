"""跑当前盘上游戏树的 13 套引擎内自检，输出全部落在本目录。

与上轮 side-view-rhythm/run_all_checks.py 的差别：
  * 追加 tests/engine_opt_check.gd
  * 输出目录改为 engine-optimization/，不覆盖上轮归档（保持它的文件清单稳定）
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = Path(__file__).resolve().parent

CHECKS = [
    "scripts/combo_check.gd",
    "tests/motion_check.gd",
    "tests/pose_probe.gd",
    "tests/duel_probe.gd",
    "tests/reach_probe.gd",
    "tests/feet_probe.gd",
    "tests/taikou_rules_check.gd",
    "tests/taikou_flow_check.gd",
    "tests/taikou_rage_check.gd",
    "tests/fighter_skin_check.gd",
    "tests/battle_motion_p0_check.gd",
    "tests/battle_rhythm_check.gd",
    "tests/engine_opt_check.gd",
]


def summary(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = [ln for ln in lines
            if ("CHECK" in ln.upper() or "PROBE" in ln.upper() or "passed" in ln.lower())
            and not ln.startswith("at:")]
    return hits[-1] if hits else (lines[-1] if lines else "<empty output>")


def main() -> int:
    report: list[str] = []
    records: list[dict] = []
    failures: list[str] = []
    for rel in CHECKS:
        try:
            proc = subprocess.run(
                [str(GODOT), "--headless", "--path", str(GAME), "--script", "res://" + rel],
                capture_output=True, timeout=180,
            )
            rc = proc.returncode
            text = (proc.stdout + b"\n" + proc.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            rc, text = -1, "TIMEOUT"
        bad = (rc != 0 or "FAIL:" in text or "SCRIPT ERROR" in text
               or "Parse Error" in text or len(text.strip()) < 20)
        line = "%-40s rc=%d  %s" % (rel, rc, summary(text))
        print(("FAIL " if bad else "OK   ") + line)
        report.append(line)
        records.append({"check": rel, "rc": rc, "ok": not bad,
                        "summary": summary(text), "stdout": text})
        if bad:
            failures.append(rel)
            report.append("      " + text[-1600:].replace("\n", "\n      "))

    report += ["", "TOTAL %d checks, %d failed" % (len(CHECKS), len(failures)),
               "RESULT: " + ("ALL GREEN" if not failures else "FAILED " + ", ".join(failures))]
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    (OUT / "check-summary.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    (OUT / "all_checks.json").write_text(
        json.dumps({"total": len(CHECKS), "failed": failures,
                    "result": "ALL GREEN" if not failures else "FAILED",
                    "checks": [{"check": r["check"], "rc": r["rc"], "ok": r["ok"],
                                "summary": r["summary"]} for r in records]},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for r in records:
        (OUT / "logs" / r["check"].replace("/", "_").replace(".gd", ".log")).write_text(
            r["stdout"], encoding="utf-8")
    print("\n".join(report[-3:]))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
