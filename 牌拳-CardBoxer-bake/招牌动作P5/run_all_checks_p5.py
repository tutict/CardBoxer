# -*- coding: utf-8 -*-
"""P5 落地后 15 套引擎内自检（清单与口径逐字沿用 P4，输出落本证据区）。

用法：python run_all_checks_p5.py
产出：data/all_checks_p5.json、logs/checks/*.out
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
LOGS = HERE / "logs" / "checks"
OUT = HERE / "data" / "all_checks_p5.json"

CHECKS = [
    ("motion_check", "res://tests/motion_check.gd"),
    ("pose_probe", "res://tests/pose_probe.gd"),
    ("duel_probe", "res://tests/duel_probe.gd"),
    ("reach_probe", "res://tests/reach_probe.gd"),
    ("feet_probe", "res://tests/feet_probe.gd"),
    ("fighter_skin_check", "res://tests/fighter_skin_check.gd"),
    ("battle_motion_p0_check", "res://tests/battle_motion_p0_check.gd"),
    ("battle_rhythm_check", "res://tests/battle_rhythm_check.gd"),
    ("engine_opt_check", "res://tests/engine_opt_check.gd"),
    ("redraw_gate_check", "res://tests/redraw_gate_check.gd"),
    ("taikou_flow_check", "res://tests/taikou_flow_check.gd"),
    ("taikou_rage_check", "res://tests/taikou_rage_check.gd"),
    ("taikou_rules_check", "res://tests/taikou_rules_check.gd"),
    ("combo_check", "res://scripts/combo_check.gd"),
    ("portrait_wiring_check", "res://tests/portrait_wiring_check.gd"),
]


def summary(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = [ln for ln in lines
            if ("CHECK" in ln.upper() or "PROBE" in ln.upper()
                or "passed" in ln.lower())
            and not ln.startswith("at:")]
    return hits[-1] if hits else (lines[-1] if lines else "<empty>")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows, failures = [], []
    for name, script in CHECKS:
        p = GAME / script.replace("res://", "")
        if not p.is_file():
            failures.append(name)
            rows.append({"name": name, "rc": -1, "ok": False,
                         "summary": "MISSING FILE"})
            print(f"FAIL {name:32s} MISSING FILE", flush=True)
            continue
        try:
            proc = subprocess.run(
                [str(GODOT), "--headless", "--path", str(GAME),
                 "--script", script],
                capture_output=True, timeout=180, cwd=str(GAME))
            rc = proc.returncode
            text = (proc.stdout + b"\n" + proc.stderr).decode(
                "utf-8", "replace")
        except subprocess.TimeoutExpired:
            rc, text = -1, "TIMEOUT"
        (LOGS / f"{name}.out").write_text(text, encoding="utf-8")
        bad = (rc != 0 or "FAIL:" in text or "SCRIPT ERROR" in text
               or "Parse Error" in text or len(text.strip()) < 20)
        rows.append({"name": name, "rc": rc, "ok": not bad,
                     "summary": summary(text)})
        if bad:
            failures.append(name)
        print(f"{'FAIL' if bad else 'PASS'} {name:32s} "
              f"{rows[-1]['summary'][:90]}", flush=True)
    report = {"checks": rows, "failed": failures,
              "passed": len(rows) - len(failures), "total": len(rows),
              "ok": not failures}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("\nALL_CHECKS_P5 %d/%d %s"
          % (report["passed"], report["total"],
             "ALL GREEN" if report["ok"] else "FAILED"))
    if failures:
        print("FAILED:", failures)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
