"""G 路线：同树同状态扫 8 组侧向视角，落盘 PNG 与结果 JSON。

用法：python run_side_view_probe.py
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUTDIR = HERE / "shots" / "side_probe"
LOGS = HERE / "logs"
OUT = HERE / "data" / "side_view_probe.json"
VIEWS = 8


def main() -> int:
    assert GODOT.is_file(), GODOT
    OUTDIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_3D_YAW", None)
    env.pop("CARD_BOXER_3D_FLIP", None)
    env["G_SIDE_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "1400",
             "--script", "res://tests/side_view_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc, text = proc.returncode, (proc.stdout + b"\n--- STDERR ---\n"
                                     + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    (LOGS / "godot_side_view_probe.log").write_text(text, encoding="utf-8")

    marker = "G_SIDE_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = payload.get("shots", [])
    has_gl = "OpenGL API" in text
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    checks = {
        "rc": rc == 0,
        "has_opengl": has_gl,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "layer_ready": payload.get("layer_ready") is True,
        "eight_views": len(rows) == VIEWS,
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file() for r in rows),
        "view_changes_all": payload.get("view_changes") == VIEWS,
        "bones_13": payload.get("bones") == 13,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "has_opengl": has_gl,
                "script_errors": errors, "headless": False},
        "views": VIEWS, "payload": payload,
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} gl={has_gl} errors={errors}")
    print(f"LAYER ready={payload.get('layer_ready')} "
          f"bones={payload.get('bones')} "
          f"view_changes={payload.get('view_changes')} "
          f"final={payload.get('final_yaw')}/{payload.get('final_flip')}")
    for r in rows:
        print(f"SHOT {r['name']:<12} {r['w']}x{r['h']} err={r['save_error']}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("SIDE_VIEW_PROBE_OK" if ok else "SIDE_VIEW_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
