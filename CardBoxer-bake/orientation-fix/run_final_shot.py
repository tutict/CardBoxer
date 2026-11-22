"""朝向订正后的引擎内验收帧：完整主场景、不隐藏 HUD、无暂停横幅。

沿用止损轮的 display_stopgap_probe.gd（live 帧在 paused 之前截，画面干净），
输出到本路线 shots/final/，不覆盖止损证据。
用法：python run_final_shot.py
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "shots" / "final"
PROBE = "res://tests/display_stopgap_probe.gd"
CLEAR = (
    "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP", "CARD_BOXER_3D_STANCE",
    "CARD_BOXER_FOE_VISUAL",
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (HERE / "logs").mkdir(parents=True, exist_ok=True)
    (HERE / "data").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    env["CARD_BOXER_3D"] = "1"
    env["DISPLAY_DIR"] = str(OUT)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script", PROBE],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    dt = round(time.perf_counter() - t0, 3)
    text = (proc.stdout + b"\n--- STDERR ---\n" + proc.stderr).decode(
        "utf-8", "replace")
    (HERE / "logs" / "godot_final.out").write_text(text, encoding="utf-8")
    marker = "DISPLAY_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    pngs = sorted(OUT.glob("display-*.png"))
    checks = {
        "rc0": proc.returncode == 0,
        "no_script_errors": (text.count("SCRIPT ERROR")
                             + text.count("Parse Error")) == 0,
        "use_3d": payload.get("use_3d") is True,
        "both_layers": (payload.get("layer_3d") is True
                        and payload.get("layer_3d_foe") is True),
        "both_overrides": (payload.get("player_override") is True
                           and payload.get("enemy_override") is True),
        "player_yaw_minus55": payload.get("p_yaw") == -55.0,
        "foe_yaw_plus55": payload.get("f_yaw") == 55.0,
        "both_no_flip": (payload.get("p_flip") is False
                         and payload.get("f_flip") is False),
        "two_pngs": len(pngs) == 2,
    }
    result = {"seconds": dt, "returncode": proc.returncode,
              "checks": checks, "payload": payload,
              "pngs": [str(p) for p in pngs],
              "ok": all(checks.values())}
    (HERE / "data" / "final_shot.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"RUN {dt}s rc={proc.returncode} pngs={len(pngs)}")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("FINAL_SHOT_OK" if result["ok"] else "FINAL_SHOT_FAILED")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
