"""Run tactical and legacy Godot checks with explicit diagnostic validation."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import time

PROJECT = Path(__file__).resolve().parents[1]
CHECKS = [
    ("tests/native_startup_check.gd", "tactical", True),
    ("tests/tactical_rules_check.gd", "tactical", True),
    ("tests/tactical_timing_check.gd", "tactical", True),
    ("tests/tactical_flow_check.gd", "tactical", True),
    ("tests/tactical_feedback_check.gd", "tactical", True),
    ("tests/tactical_strategy_check.gd", "tactical", True),
    ("tests/tactical_forecast_check.gd", "tactical", True),
    ("tests/tactical_planning_check.gd", "tactical", True),
    ("tests/tactical_match_check.gd", "tactical", True),
    ("tests/tactical_integration_check.gd", "tactical", True),
    ("tests/tactical_ui_check.gd", "tactical", True),
    ("tests/tactical_ui_optimization_check.gd", "tactical", True),
    ("tests/tactical_contact_check.gd", "tactical", True),
    ("tests/taikou_rules_check.gd", "taikou", True),
    ("tests/taikou_rage_check.gd", "taikou", True),
    ("tests/taikou_flow_check.gd", "taikou", True),
    ("scripts/combo_check.gd", "realtime", True),
    ("tests/battle_motion_p0_check.gd", "taikou", True),
    ("tests/battle_rhythm_check.gd", "taikou", True),
    ("tests/battle_presentation_check.gd", "taikou", True),
    ("tests/battle_integration_check.gd", "taikou", True),
    ("tests/battle_contact_spacing_check.gd", "taikou", True),
    ("tests/battle_shadow_check.gd", "taikou", True),
    ("tests/battle_transition_check.gd", "taikou", True),
    ("tests/native_motion_check.gd", "taikou", True),
    ("tests/redraw_gate_check.gd", "taikou", True),
    ("tests/engine_opt_check.gd", "taikou", True),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", default=str(Path.home()/"Documents/godot/Godot_v4.5-stable_win64_console.exe"))
    parser.add_argument("--output", type=Path, default=PROJECT.parent/"logs/full-suite")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for script, mode, native in CHECKS:
        env = os.environ.copy()
        env.update(CARD_BOXER_BATTLE_MODE=mode, CARD_BOXER_3D="1",
                   CARD_BOXER_SEED="2026", CARD_BOXER_CAPTURE="", CARD_BOXER_TACTICAL_BOT="",
                   CARD_BOXER_TAIKOU_BOT="", CARD_BOXER_BOT="")
        name = Path(script).stem
        started = time.monotonic()
        proc = subprocess.run([args.godot,"--headless","--path",str(PROJECT),"--log-file",
                               str(args.output/(name+".engine.log")),"--script","res://"+script],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        output = proc.stdout.decode("utf-8",errors="replace")
        (args.output/(name+".out")).write_text(output,encoding="utf-8")
        counts = re.findall(r"(\d+)/(\d+) passed",output)
        bad = "SCRIPT ERROR:" in output or "FAIL:" in output or any(a!=b for a,b in counts)
        unexpected = [line for line in output.splitlines() if line.startswith("ERROR:")
                      and "root certificate store" not in line and "resources still in use" not in line]
        passed = proc.returncode == 0 and not bad and not unexpected and "pass" in output.lower()
        result = {"script":script,"mode":mode,"native":native,"passed":passed,
                  "exit_code":proc.returncode,"seconds":round(time.monotonic()-started,2),
                  "counts":counts,"unexpected_errors":unexpected}
        results.append(result)
        print(("PASS " if passed else "FAIL ")+name+" "+str(result["seconds"])+"s",flush=True)
        if not passed:
            print("\n".join(output.splitlines()[-20:]),flush=True)
    report = {"passed":sum(item["passed"] for item in results),"total":len(results),"results":results}
    (args.output/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"FULL SUITE: {report['passed']}/{report['total']} scripts passed",flush=True)
    return 0 if report["passed"]==report["total"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
