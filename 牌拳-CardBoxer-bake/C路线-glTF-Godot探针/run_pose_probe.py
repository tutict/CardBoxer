"""驱动 probe_project/probes/pose_probe.gd，把 POSE_JSON 落盘。

只读已导入的隔离工程，不改游戏工程。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "probe_project"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "godot_pose_result.json"
LOG = HERE / "logs" / "godot_pose_probe.log"


def main() -> int:
    t0 = time.perf_counter()
    cmd = [str(GODOT), "--headless", "--path", str(PROJECT),
           "--script", "res://probes/pose_probe.gd"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        stdout, stderr, rc = r.stdout or "", r.stderr or "", r.returncode
    except subprocess.TimeoutExpired as exc:
        # GDScript 抛错时 quit() 不执行，SceneTree 会无限空转。
        # 超时必须把部分输出留下，否则根因会被「挂住」两个字盖掉。
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        rc = -1
        LOG.write_text(stdout + "\n=== STDERR ===\n" + stderr
                       + "\n=== TIMEOUT ===\n"
                       + f"No POSE_JSON within 60s; cmd={cmd!r}\n",
                       encoding="utf-8")
        print("POSE_PROBE_TIMEOUT " + repr((stdout + stderr)[:500]))
        return 1
    elapsed = round(time.perf_counter() - t0, 3)
    LOG.write_text(stdout + "\n=== STDERR ===\n" + stderr, encoding="utf-8")
    marker = "POSE_JSON "
    line = next((l for l in stdout.splitlines()
                 if l.startswith(marker)), None)
    if line is None:
        print("POSE_JSON_MISSING rc=" + str(rc)
              + " stdout_head=" + repr(stdout[:300])
              + " stderr_head=" + repr(stderr[:300]))
        return 1
    data = json.loads(line[len(marker):])
    data["seconds"] = elapsed
    data["returncode"] = rc
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"POSE_PROBE seconds={elapsed} rc={rc}")
    print("POSE " + json.dumps({k: v for k, v in data.items()
                                if k not in ("meshes",)}, ensure_ascii=False))
    for m in data.get("meshes", []):
        print(f"  MESH {m['name']:<20} skeleton_path={m['skeleton_path']!r} "
              f"skin_present={m['skin_present']}")
    ok = (data.get("load_ok") and data.get("skeleton_found")
          and data.get("pose_local_changed")
          and data.get("bound_mesh_count", 0) >= 1
          and data.get("unbound_mesh_count", 0) >= 1)
    print("GODOT_POSE_PROBE_OK" if ok else "GODOT_POSE_PROBE_INCOMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
