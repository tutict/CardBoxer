"""Fresh applicable Godot checks, three isolated headless processes at a time."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess

TASK = Path(__file__).resolve().parent.parent
GODOT = "C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe"
PROJECT = TASK / "project"
TESTS = ["taikou_rules_check", "taikou_rage_check", "taikou_flow_check",
         "battle_rhythm_check", "battle_motion_p0_check", "motion_check",
         "engine_opt_check", "fighter_skin_check", "portrait_wiring_check",
         "redraw_gate_check", "battle_presentation_check", "battle_transition_check",
         "battle_integration_check", "native_motion_check", "native_rig_check"]
if (PROJECT / "tests/natural_runtime_check.gd").is_file():
    TESTS.append("natural_runtime_check")


def run(name: str) -> dict:
    path = PROJECT / "tests" / (name + ".gd")
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("CARD_BOXER_") or key.startswith("NATIVE_"):
            env.pop(key, None)
    command = [GODOT, "--headless", "--path", str(PROJECT), "--log-file",
               str(TASK / "logs" / ("final-"+name+"-engine.log")),
               "--script", "res://tests/"+path.name]
    done = subprocess.run(command, capture_output=True, env=env, timeout=180,
                          creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    output = done.stdout.decode("utf-8",errors="replace") + done.stderr.decode("utf-8",errors="replace")
    (TASK / "logs" / ("final-"+name+".log")).write_text(output,encoding="utf-8")
    errors = any(marker in output for marker in
                 ("SCRIPT ERROR:","Parse Error:","Failed to load script","FAIL:"))
    row = {"name":name,"ok":done.returncode==0 and not errors,
           "exit_code":done.returncode,"summary":[line for line in output.splitlines()
            if "CHECK" in line or "PASS" in line or "FAIL" in line]}
    print(name + ": " + ("PASS" if row["ok"] else "FAIL"),flush=True)
    return row


if __name__ == "__main__":
    tests = list(TESTS)
    # New owned check scripts are included if present, excluding rendered/harness entry points.
    for path in (PROJECT/"tests").glob("battle_*check.gd"):
        if path.stem not in tests:
            tests.append(path.stem)
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(run,tests))
    result = {"ok":all(row["ok"] for row in rows),"checks":rows}
    (TASK/"reports/final-checks.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"FINAL_CHECKS: {'PASS' if result['ok'] else 'FAIL'} ({len(rows)} suites)")
    raise SystemExit(0 if result["ok"] else 1)
