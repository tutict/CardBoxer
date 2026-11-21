"""动作表现 P2 · 15 套引擎内自检（输出全落本证据区）。

清单与口径逐字沿用 动作覆盖P1/run_all_checks_p1.py，只把 LOGS / OUT
改到本区，不覆盖任何历史归档。用法：python run_all_checks_p2.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
LOGS = HERE / "logs" / "checks"
OUT = HERE / "data" / "all_checks_p2.json"

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
    return hits[-1] if hits else (lines[-1] if lines else "<empty output>")


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
        bad = (rc != 0 or "FAIL:" in text or "SCRIPT ERROR" in text
               or "Parse Error" in text or len(text.strip()) < 20)
        rows.append({"name": name, "rc": rc, "ok": not bad,
                     "summary": summary(text)})
        (LOGS / f"p2_{name}.log").write_text(text, encoding="utf-8")
        if bad:
            failures.append(name)
        print(("FAIL " if bad else "OK   ") +
              f"{name:32s} rc={rc}  {summary(text)}", flush=True)
    payload = {"tag": "motion_p2", "total": len(CHECKS),
               "failed": failures,
               "result": "ALL GREEN" if not failures else "FAILED",
               "checks": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"ALL_CHECKS_P2 {len(CHECKS) - len(failures)}/{len(CHECKS)} "
          f"{payload['result']}", flush=True)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
