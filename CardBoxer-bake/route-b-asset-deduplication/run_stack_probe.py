"""B 路线 P0：跑引擎内 4 状态探针，落盘 SubViewport 原图与材质槽位读回。

只读游戏资产；只往工程 tests/ 放一个探针脚本，不改任何 .gd 玩法源码、
不改 GLB / 贴图 / project.godot。
用法：python run_stack_probe.py
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
SRC = HERE / "tests" / "stack_probe.gd"
DST = GAME / "tests" / "stack_probe.gd"
OUTDIR = HERE / "shots" / "stack_probe"
OUT = HERE / "data" / "stack_probe.json"
LOG = HERE / "logs" / "godot_stack_probe.log"
MARKER = "STACK_JSON "


def main() -> int:
    assert GODOT.is_file(), GODOT
    assert SRC.is_file(), SRC
    OUTDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    for k in ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW",
              "CARD_BOXER_3D_FLIP", "CARD_BOXER_3D_STANCE"):
        env.pop(k, None)
    env["CARD_BOXER_FOE_VISUAL"] = "none"
    env["STACK_OUT"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900", "--script",
             "res://tests/stack_probe.gd"],
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
    shots = payload.get("shots", [])
    slots = payload.get("material_slots", [])
    checks = {
        "rc": rc == 0,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "five_states": len(shots) == 5,
        "final_yaw_is_neg55": abs(payload.get("yaw", 0.0) + 55.0) < 0.01,
        "all_png_ok": all(
            r.get("save_error") == 0 and Path(r.get("path", "")).is_file()
            for r in shots),
        "glb_is_foe": payload.get("glb_path", "").endswith(
            "foe-rigged.glb"),
        "role_is_foe": payload.get("role") == "foe",
        "four_lights": payload.get("lights") == 4,
        "one_mesh": payload.get("mesh_rows") == 1,
        "slots_readback": len(slots) == 1
                          and "albedo_texture" in slots[0],
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "script_errors": errors},
        "out_dir": str(OUTDIR), "payload": payload, "checks": checks,
        "failed": [k for k, v in checks.items() if not v], "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} errors={errors}")
    print("MATERIAL_SLOTS", json.dumps(slots, ensure_ascii=False)[:900])
    print("LIGHTS", payload.get("lights"), payload.get("light_energy0"))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("STACK_PROBE_OK" if ok else "STACK_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
