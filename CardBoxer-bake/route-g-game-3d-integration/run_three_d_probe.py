"""G 路线：同进程同树 3D 双轨 A/B 探针驱动。

用法：python run_three_d_probe.py
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
OUTDIR = HERE / "shots" / "ab_same_tree"
LOGS = HERE / "logs"
OUT = HERE / "data" / "three_d_ab.json"


def main() -> int:
    assert GODOT.is_file(), GODOT
    OUTDIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)      # 探针自己挂层，off 阶段必须无 3D
    env["G_3D_AB_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900",
             "--script", "res://tests/three_d_probe.gd"],
            env=env, capture_output=True, timeout=240, cwd=str(GAME))
        rc, text = proc.returncode, (proc.stdout + b"\n--- STDERR ---\n"
                                     + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    (LOGS / "godot_three_d_ab.log").write_text(text, encoding="utf-8")

    marker = "G3D_AB_JSON "
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
        "four_shots": len(rows) == 4,
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file() for r in rows),
        "bones_13": payload.get("bones") == 13,
        "frames_applied_positive": int(payload.get("frames_applied", 0)) > 0,
        "tex_drawn": payload.get("tex_drawn") is True,
        "override_on": payload.get("draw_3d_override") is True,
        "env_not_preset": payload.get("use_3d_env") == "",
        "last_frame_is_wave17": payload.get("last_card") == "wave"
                                and payload.get("last_frame") == 17,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "has_opengl": has_gl,
                "script_errors": errors, "headless": False},
        "payload": payload,
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} gl={has_gl} errors={errors}")
    print(f"LAYER ready={payload.get('layer_ready')} "
          f"bones={payload.get('bones')} "
          f"frames_applied={payload.get('frames_applied')} "
          f"tex_drawn={payload.get('tex_drawn')}")
    for r in rows:
        print(f"SHOT {r['name']:<12} {r['w']}x{r['h']} err={r['save_error']} "
              f"prims={r['prims_mean']:.0f} calls={r['draw_calls_mean']:.1f}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("THREE_D_AB_OK" if ok else "THREE_D_AB_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
