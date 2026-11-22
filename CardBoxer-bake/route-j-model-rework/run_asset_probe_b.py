"""B 路线：装好 B GLB 后跑引擎内资产读回 + 三张同进程截帧。

与 J 的 asset_probe 用同一份 GDScript（tests/asset_probe_j.gd），
但输出独立落 shots/asset_b/，不覆盖 v1 / r1 的既有证据。
用法：python run_asset_probe_b.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUTDIR = HERE / "shots" / "asset_b"
SRC = HERE / "tests" / "asset_probe_j.gd"
DST = GAME / "tests" / "asset_probe_j.gd"
OUT = HERE / "data" / "asset_probe_b.json"
LOG = HERE / "logs" / "godot_asset_probe_b.log"


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_FOE_VISUAL", None)
    env["J_ASSET_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900", "--script",
             "res://tests/asset_probe_j.gd"],
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
    marker = "JASSET_JSON "
    line = next((l for l in text.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    foe, player = payload.get("foe", {}), payload.get("player", {})
    fmesh = foe.get("meshes", [{}])
    pmesh = player.get("meshes", [{}])
    checks = {
        "rc": rc == 0,
        "has_opengl": "OpenGL API" in text,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "three_shots": len(payload.get("shots", [])) == 3,
        "all_png_ok": all(r.get("save_error") == 0
                          and Path(r.get("path", "")).is_file()
                          for r in payload.get("shots", [])),
        "both_sv_png_written": all(
            (OUTDIR / f"j-sv-{role}.png").is_file()
            for role in ("foe", "player")),
        "both_albedo_png_written": all(
            (OUTDIR / f"j-albedo-{role}.png").is_file()
            for role in ("foe", "player")),
        "sv_rids_differ": (
            foe.get("tex_instance_id") != player.get("tex_instance_id")
            and foe.get("sv_instance_id") != player.get("sv_instance_id")),
        "glb_paths_differ": foe.get("glb_path") != player.get("glb_path"),
        "albedo_paths_differ": (
            fmesh[0].get("albedo") != pmesh[0].get("albedo")
            if fmesh and pmesh else False),
        "foe_verts": fmesh[0].get("verts") if fmesh else 0,
        "player_verts": pmesh[0].get("verts") if pmesh else 0,
    }
    bool_checks = {k: v for k, v in checks.items() if isinstance(v, bool)}
    ok = all(bool_checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "script_errors": errors},
        "out_dir": str(OUTDIR), "payload": payload, "checks": checks,
        "bool_failed": [k for k, v in bool_checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} errors={errors}")
    for role in ("foe", "player"):
        d = payload.get(role, {})
        print("LAYER", role, d.get("glb_path"), d.get("meshes"))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("ASSET_PROBE_B_OK" if ok else "ASSET_PROBE_B_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
