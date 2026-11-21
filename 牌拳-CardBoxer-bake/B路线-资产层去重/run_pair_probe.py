"""按用户实际运行路径（完整主场景 + CARD_BOXER_3D=1）取两层当前状态。

用法：python run_pair_probe.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "current_pair_probe.gd"
DST = GAME / "tests" / "current_pair_probe.gd"
OUTDIR = HERE / "shots" / "current_pair"
OUT = HERE / "data" / "current_pair.json"
LOG = HERE / "logs" / "godot_current_pair.log"
MARKER = "PAIR_JSON "


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    for k in ("CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
              "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL"):
        env.pop(k, None)
    env["CARD_BOXER_3D"] = "1"
    env["PAIR_OUT"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900", "--script",
             "res://tests/current_pair_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = proc.returncode
        text = (proc.stdout + b"\n--- STDERR ---\n"
                + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(MARKER)), None)
    payload = json.loads(line[len(MARKER):]) if line else {"error": "no marker"}
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    p, f = payload.get("player", {}), payload.get("foe", {})
    pm = p.get("meshes", [{}])
    fm = f.get("meshes", [{}])
    checks = {
        "rc": rc == 0,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "use_3d": payload.get("use_3d") is True,
        "both_layers": p.get("present") is True
                       and f.get("present") is True,
        "glb_paths_differ": p.get("glb_path") != f.get("glb_path"),
        "foe_glb_is_foe": str(f.get("glb_path", "")).endswith(
            "foe-rigged.glb"),
        "player_glb_is_player": str(p.get("glb_path", "")).endswith(
            "player-rigged.glb"),
        "both_sv_written": all(
            Path(d.get("sv_png", "")).is_file()
            and d.get("sv_error") == 0 for d in (p, f)),
        "full_frame_written": Path(
            payload.get("full_frame", {}).get("path", "")).is_file(),
        "albedo_paths_differ": (
            (pm[0].get("albedo", "") if pm else "")
            != (fm[0].get("albedo", "") if fm else "")),
        "player_verts_57934": (pm[0].get("verts") if pm else 0) == 57934,
        "foe_verts_64059": (fm[0].get("verts") if fm else 0) == 64059,
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "script_errors": errors},
        "payload": payload, "checks": checks,
        "failed": [k for k, v in checks.items() if not v], "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} errors={errors}")
    for role, d in (("player", p), ("foe", f)):
        print(role.upper(), d.get("glb_path"), "yaw", d.get("yaw"),
              "meshes", d.get("meshes"))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PAIR_PROBE_OK" if ok else "PAIR_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
