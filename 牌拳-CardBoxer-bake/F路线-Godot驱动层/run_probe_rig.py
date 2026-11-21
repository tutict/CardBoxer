"""阶段 4a：把带 skin 的 GLB 与运动输入放进隔离工程，headless 量骨骼基底。

只读 F 路线已交付的 player-rigged.glb / motion_input.json，不回写归档；
Godot 编辑器导入可以 headless，渲染才需要带窗口。
用法：python run_probe_rig.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "probe_project_f"
ASSETS = PROJECT / "assets"
DATA = PROJECT / "data"
LOGS = HERE / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
GLB = "player-rigged.glb"
MOTION = "motion_input.json"
OUT = HERE / "data" / "godot_rig_probe.json"


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
    for d in (ASSETS, DATA, LOGS, OUT.parent):
        d.mkdir(parents=True, exist_ok=True)

    copies = []
    for src, dst in ((HERE / GLB, ASSETS / GLB),
                     (HERE / "data" / MOTION, DATA / MOTION)):
        assert src.is_file(), src
        shutil.copyfile(src, dst)
        copies.append({"src": str(src), "dst": str(dst),
                       "bytes": dst.stat().st_size,
                       "sha256": sha256(src),
                       "identical": sha256(src) == sha256(dst)})
    assert all(c["identical"] for c in copies), copies

    env = os.environ.copy()
    dt_import, rc_import, _ = run(
        [str(GODOT), "--headless", "--editor", "--quit",
         "--path", str(PROJECT)],
        env, 300, LOGS / "godot_editor_import_f.log")
    import_ok = (ASSETS / (GLB + ".import")).is_file()

    dt_probe, rc_probe, log_probe = run(
        [str(GODOT), "--headless", "--path", str(PROJECT),
         "--script", "res://probes/probe_rig.gd"],
        env, 300, LOGS / "godot_probe_rig.log")

    marker = "RIG_JSON "
    line = next((l for l in log_probe.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no RIG_JSON"}
    errors = log_probe.count("SCRIPT ERROR")
    ok = (rc_import == 0 and import_ok and rc_probe == 0 and errors == 0
          and payload.get("load_ok") is True
          and payload.get("skeleton_found") is True
          and payload.get("bone_count") == 14
          and payload.get("pose_writable") is True)
    out = {
        "godot": str(GODOT),
        "probe_project": str(PROJECT),
        "copies": copies,
        "editor_import": {"seconds": dt_import, "returncode": rc_import,
                          "import_file": import_ok},
        "probe": {"seconds": dt_probe, "returncode": rc_probe,
                  "script_errors": errors, "headless": True},
        "rig": payload,
        "ok": ok,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"IMPORT rc={rc_import} {dt_import}s file={import_ok}")
    print(f"PROBE  rc={rc_probe} {dt_probe}s errors={errors}")
    print(f"BONES  {payload.get('bone_count')} "
          f"writable={payload.get('pose_writable')} "
          f"meshes={len(payload.get('meshes', []))}")
    print("GODOT_RIG_PROBE_OK" if ok else "GODOT_RIG_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
