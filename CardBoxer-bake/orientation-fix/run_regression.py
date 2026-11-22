"""回归两件事：① 默认关 3D 仍零污染；② 回合制玩法自检仍全绿。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
CLEAR = (
    "CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
    "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
)


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    return env


def run_default() -> dict:
    out = HERE / "shots" / "regression-default"
    out.mkdir(parents=True, exist_ok=True)
    env = base_env()
    env["DISPLAY_DIR"] = str(out)
    p = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script",
         "res://tests/display_stopgap_probe.gd"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode(
        "utf-8", "replace")
    (HERE / "logs" / "godot_regression_default.out").write_text(
        text, encoding="utf-8")
    marker = "DISPLAY_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    return {
        "rc": p.returncode,
        "script_errors": text.count("SCRIPT ERROR") + text.count("Parse Error"),
        "payload": payload,
        "pngs": len(list(out.glob("display-*.png"))),
    }


def run_taikou() -> dict:
    env = base_env()
    p = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME), "--script",
         "res://tests/taikou_flow_check.gd"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode(
        "utf-8", "replace")
    (HERE / "logs" / "godot_regression_taikou.out").write_text(
        text, encoding="utf-8")
    return {"rc": p.returncode,
            "all_51": "TAIKOU FLOW CHECK: 51/51 passed" in text,
            "script_errors": text.count("SCRIPT ERROR")
            + text.count("Parse Error")}


def main() -> int:
    (HERE / "logs").mkdir(parents=True, exist_ok=True)
    (HERE / "data").mkdir(parents=True, exist_ok=True)
    d, t = run_default(), run_taikou()
    pay = d["payload"]
    checks = {
        "default_rc0": d["rc"] == 0,
        "default_no_script_errors": d["script_errors"] == 0,
        "default_use_3d_false": pay.get("use_3d") is False,
        "default_no_layers": (pay.get("layer_3d") is False
                              and pay.get("layer_3d_foe") is False),
        "default_no_overrides": (pay.get("player_override") is False
                                 and pay.get("enemy_override") is False),
        "default_no_yaw_read": (pay.get("p_yaw") == 0.0
                                and pay.get("f_yaw") == 0.0),
        "default_two_pngs": d["pngs"] == 2,
        "taikou_rc0": t["rc"] == 0,
        "taikou_51_of_51": t["all_51"],
        "taikou_no_script_errors": t["script_errors"] == 0,
    }
    ok = all(checks.values())
    (HERE / "data" / "regression.json").write_text(
        json.dumps({"checks": checks, "default_payload": pay,
                    "taikou": t, "ok": ok}, ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print(f"PASSED {sum(checks.values())}/{len(checks)}")
    print("REGRESSION_OK" if ok else "REGRESSION_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
