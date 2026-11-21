"""阶段 4b 驱动：带窗口跑 73 帧驱动探针，落盘数值结果。

必须带窗口：headless 不发 frame_post_draw，Skeleton3D 的 global pose
脏标记不刷新，get_bone_global_pose 会一直返回 rest。
用法：python run_probe_drive.py
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "probe_project_f"
LOGS = HERE / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "data" / "godot_drive_probe.json"


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
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    dt, rc, log = run(
        [str(GODOT), "--path", str(PROJECT),
         "--resolution", "900x1100",
         "--script", "res://probes/probe_drive.gd",
         "--quit-after", "120000"],
        env, 300, LOGS / "godot_probe_drive.log")
    marker = "DRIVE_JSON "
    line = next((l for l in log.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no DRIVE_JSON"}
    errors = log.count("SCRIPT ERROR")
    has_gl = "OpenGL API" in log
    ok = (rc == 0 and errors == 0 and has_gl
          and payload.get("frame_count") == 73
          and payload.get("frames_applied") == 73
          and payload.get("bone_count") == 14)
    OUT.write_text(json.dumps({
        "godot": str(GODOT),
        "probe": {"seconds": dt, "returncode": rc,
                  "script_errors": errors, "headless": False,
                  "has_opengl": has_gl},
        "result": payload,
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DRIVE rc={rc} {dt}s errors={errors} gl={has_gl} "
          f"frames={payload.get('frame_count')} "
          f"bones={payload.get('bone_count')} "
          f"applied={payload.get('frames_applied')}")
    print("GODOT_DRIVE_PROBE_OK" if ok else "GODOT_DRIVE_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
