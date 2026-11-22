"""朝向扫描：打开 3D，同进程扫玩家/对手各 4 组 yaw×flip，出 9 张整帧 + 2 张 SV 原图。

用法：python run_orientation_probe.py
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
SRC = HERE / "tests" / "orientation_probe.gd"
DST = GAME / "tests" / "orientation_probe.gd"
OUTDIR = HERE / "shots"
PROBE = "res://tests/orientation_probe.gd"
CLEAR = (
    "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP", "CARD_BOXER_3D_STANCE",
    "CARD_BOXER_FOE_VISUAL",
)


def main() -> int:
    assert GODOT.is_file() and DST.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (HERE / "logs").mkdir(parents=True, exist_ok=True)
    (HERE / "data").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    env["CARD_BOXER_3D"] = "1"
    env["ORIENT_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "1200", "--script", PROBE],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    dt = round(time.perf_counter() - t0, 3)
    text = (proc.stdout + b"\n--- STDERR ---\n" + proc.stderr).decode(
        "utf-8", "replace")
    (HERE / "logs" / "godot_orientation.out").write_text(
        text, encoding="utf-8")
    marker = "ORIENT_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    shots = payload.get("shots", [])
    checks = {
        "rc0": proc.returncode == 0,
        "no_script_errors": (text.count("SCRIPT ERROR")
                             + text.count("Parse Error")) == 0,
        "nine_shots": len(shots) == 9,
        "all_1280x720": all(s.get("w") == 1280 and s.get("h") == 720
                            and s.get("save_error") == 0 for s in shots),
        "two_sv_pngs": all((OUTDIR / f"o-sv-{r}.png").is_file()
                           for r in ("player", "foe")),
        "yaw_flip_recorded": all(
            "p_yaw" in s and "p_flip" in s and "f_yaw" in s
            and "f_flip" in s for s in shots),
    }
    result = {"seconds": dt, "returncode": proc.returncode,
              "checks": checks, "payload": payload,
              "ok": all(checks.values())}
    (HERE / "data" / "orientation_probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"RUN {dt}s rc={proc.returncode} shots={len(shots)}")
    for k, v in checks.items():
        print("CHECK", k, v)
    for s in shots:
        print("SHOT", s.get("name"), "p", s.get("p_yaw"), s.get("p_flip"),
              "f", s.get("f_yaw"), s.get("f_flip"))
    print("ORIENT_PROBE_OK" if result["ok"] else "ORIENT_PROBE_FAILED")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
