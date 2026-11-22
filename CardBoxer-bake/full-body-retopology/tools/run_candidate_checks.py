"""Run the final candidate's existing runtime acceptance with owned engine logs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

TASK = Path(__file__).resolve().parent.parent
PROJECT = TASK / "project"
GODOT = Path("C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe")
SUITES = (
    "taikou_rules_check", "taikou_rage_check", "taikou_flow_check",
    "battle_rhythm_check", "battle_motion_p0_check", "motion_check",
    "engine_opt_check", "fighter_skin_check", "portrait_wiring_check",
    "redraw_gate_check", "battle_presentation_check", "battle_transition_check",
    "battle_integration_check", "native_motion_check", "native_rig_check",
    "natural_runtime_check", "battle_contact_spacing_check", "battle_shadow_check",
    "hand_shape_check", "hand_asset_check", "hand_body_invariance_check",
)
ERRORS = ("SCRIPT ERROR:", "Parse Error:", "Failed to load script", "FAIL:", "CrashHandlerException")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def motion_contract() -> dict:
    before = json.loads((TASK / "baseline/data/combat_motion_3d.json").read_text(encoding="utf-8"))
    after = json.loads((PROJECT / "data/combat_motion_3d.json").read_text(encoding="utf-8"))
    body = copy.deepcopy(after)
    keys = 0
    roles = {}
    for role, data in body["roles"].items():
        roles[role] = list(data["clips"])
        for clip in data["clips"].values():
            for key in clip["keys"]:
                grip = key.pop("hand_grip", None)
                if not isinstance(grip, list) or len(grip) != 2 or any(
                    isinstance(g, bool) or not isinstance(g, (int, float)) or not 0 <= g <= 1
                    for g in grip
                ):
                    raise AssertionError("Invalid authored progressive hand key")
                keys += 1
    if body != before:
        raise AssertionError("Original body quaternion/root/phase data changed")
    result = {"ok": True, "keys": keys, "roles": roles, "body_and_phase_exact": True,
              "baseline_sha256": digest(TASK / "baseline/data/combat_motion_3d.json"),
              "candidate_sha256": digest(PROJECT / "data/combat_motion_3d.json")}
    (TASK / "reports/body-motion-contract.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run(name: str, mode: str = "") -> dict:
    tag = name + ("-3d-" + mode if mode else "")
    log = (TASK / "logs" / ("candidate-" + tag + "-engine.log")).resolve()
    args = [str(GODOT), "--headless", "--path", str(PROJECT), "--log-file", str(log)]
    if name == "import":
        args += ["--editor", "--import"]
    else:
        script = str(TASK / "tools/check_hand_body.gd") if name == "hand_body_invariance_check" else "res://tests/" + name + ".gd"
        args += ["--script", script]
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(("CARD_BOXER_", "NATIVE_", "MODEL_DETAIL_", "NATURAL_")):
            env.pop(key, None)
    if mode:
        env["CARD_BOXER_3D"] = "1"
        env["CARD_BOXER_BATTLE_MODE"] = mode
    output_log = TASK / "logs" / ("candidate-" + tag + "-output.log")
    try:
        done = subprocess.run(args, env=env, capture_output=True, timeout=240,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = (done.stdout + done.stderr).decode("utf-8", errors="replace")
        code = done.returncode
    except subprocess.TimeoutExpired as error:
        output = ((error.stdout or b"") + (error.stderr or b"")).decode("utf-8", errors="replace")
        output += "\nFAIL: engine verification timed out\n"
        code = -1
    output_log.write_text(output, encoding="utf-8")
    row = {"name": tag, "ok": code == 0 and not any(marker in output for marker in ERRORS),
           "exit_code": code, "command": args, "engine_log": str(log), "output_log": str(output_log),
           "summary": [line for line in output.splitlines() if "CHECK" in line or "PASS" in line or "FAIL" in line]}
    print(tag + (": PASS" if row["ok"] else ": FAIL"), flush=True)
    return row


def main() -> None:
    contract = motion_contract()
    rows = [run("import")]
    if rows[0]["ok"]:
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows += list(pool.map(run, SUITES))
        for mode in ("taikou", "realtime"):
            rows.append(run("battle_integration_check", mode))
    result = {"ok": all(row["ok"] for row in rows), "motion_contract": contract,
              "checks": rows, "scope": "Existing relevant runtime suites plus actual imported hand/socket arrays; both 3D modes"}
    (TASK / "reports/candidate-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CANDIDATE_CHECKS: {'PASS' if result['ok'] else 'FAIL'} ({len(rows)} suites; {contract['keys']} unchanged body keys)")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
