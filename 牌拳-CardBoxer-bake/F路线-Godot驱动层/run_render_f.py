"""阶段 5 驱动：带窗口跑引擎内 9 帧截帧，落盘 PNG 与报告。

用法：python run_render_f.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "probe_project_f"
SHOTS = HERE / "shots"
LOGS = HERE / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "data" / "godot_render_f.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], env: dict, timeout: int, log: Path):
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, timeout=timeout)
        code, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as exc:
        code = -1
        out = exc.stdout or b""
        err = (exc.stderr or b"") + b"\n=== TIMEOUT ===\n"
    text = (out + b"\n=== STDERR ===\n" + err).decode("utf-8", "replace")
    log.write_text(text, encoding="utf-8")
    return round(time.perf_counter() - t0, 3), code, text


def main() -> int:
    assert GODOT.is_file(), GODOT
    SHOTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["F_SHOT_DIR"] = str(SHOTS)
    dt, rc, log = run(
        [str(GODOT), "--path", str(PROJECT),
         "--resolution", "900x1100",
         "--script", "res://probes/render_driven.gd",
         "--quit-after", "6000"],
        env, 300, LOGS / "godot_render_driven.log")
    marker = "RENDER_JSON "
    line = next((l for l in log.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no RENDER_JSON"}
    rows = payload.get("shots", [])
    pngs = []
    for row in rows:
        p = Path(row["path"])
        pngs.append({
            "name": row["name"], "seq": row["seq"], "yaw": row["yaw"],
            "card": row["card"], "frame": row["frame"],
            "root_m": row["root_m"],
            "path": str(p), "exists": p.is_file(),
            "bytes": p.stat().st_size if p.is_file() else 0,
            "sha256": sha256(p) if p.is_file() else "",
            "w": row.get("w"), "h": row.get("h"),
            "save_error": row.get("save_error"),
        })
    has_gl = "OpenGL API" in log
    errors = log.count("SCRIPT ERROR")
    ok = (rc == 0 and has_gl and errors == 0 and "error" not in payload
          and payload.get("stage_ready") is True
          and len(pngs) == 9
          and all(x["exists"] and x["bytes"] > 20000
                  and x["save_error"] == 0
                  and x["w"] == 900 and x["h"] == 1100 for x in pngs))
    OUT.write_text(json.dumps({
        "godot": str(GODOT),
        "probe_project": str(PROJECT),
        "main_scene": "res://scenes/player_driven.tscn",
        "render": {"seconds": dt, "returncode": rc,
                   "has_opengl": has_gl, "script_errors": errors,
                   "headless": False},
        "stage_ready": payload.get("stage_ready"),
        "frames_applied": payload.get("frames_applied"),
        "pngs": pngs,
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for x in pngs:
        print(f"SHOT {x['name']:<20} {x['w']}x{x['h']} "
              f"{x['bytes']:>8} B err={x['save_error']} "
              f"card={x['card']}/{x['frame']}")
    print(f"RENDER seconds={dt} rc={rc} gl={has_gl} errs={errors} "
          f"stage_ready={payload.get('stage_ready')} shots={len(pngs)}")
    print("GODOT_RENDER_F_OK" if ok else "GODOT_RENDER_F_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
