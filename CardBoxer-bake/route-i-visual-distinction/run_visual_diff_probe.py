"""I 路线 P3：同进程同树「视觉区分 on / plain / again」A/B 探针驱动。

把 tests/visual_diff_probe.gd 复制进游戏工程（新增文件，不改既有），
带窗口跑 Godot 4.5，解析 IVIS_JSON 并写判据。
用法：python run_visual_diff_probe.py
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
OUTDIR = HERE / "shots" / "visual_ab"
SRC = HERE / "tests" / "visual_diff_probe.gd"
DST = GAME / "tests" / "visual_diff_probe.gd"
OUT = HERE / "data" / "visual_ab_i.json"
LOG = HERE / "logs" / "godot_visual_diff.log"


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_FOE_VISUAL", None)   # 让 configure("foe") 默认启用
    env["I_VIS_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900", "--script",
             "res://tests/visual_diff_probe.gd"],
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
    marker = "IVIS_JSON "
    line = next((l for l in text.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = payload.get("shots", [])
    states = {s.get("tag"): s for s in payload.get("states", [])}
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    checks = {
        "rc": rc == 0,
        "has_opengl": "OpenGL API" in text,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "five_shots": len(rows) == 5,
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file()
                          for r in rows),
        "both_layers_ready": (payload.get("player_layer_ready") is True
                              and payload.get("foe_layer_ready") is True),
        "env_not_none": payload.get("env_visual_none") == "",
        "on_state_enabled": states.get("on", {}).get("foe_visual") is True,
        "plain_state_disabled": (states.get("plain", {}).get("foe_visual")
                                 is False),
        "again_state_enabled": (states.get("again", {}).get("foe_visual")
                                is True),
        "player_layer_never_visual": (
            payload.get("player_visual_state", {}).get("foe_visual") is False),
        "mesh_and_lights_collected": all(
            states.get(t, {}).get("mesh_rows", 0) > 0
            and states.get(t, {}).get("light_rows", 0) == 4
            for t in ("on", "plain", "again")),
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc,
                "has_opengl": "OpenGL API" in text,
                "script_errors": errors, "headless": False},
        "payload": payload, "checks": checks,
        "failed": [k for k, v in checks.items() if not v], "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} errors={errors}")
    for s in payload.get("states", []):
        print("STATE", s)
    print("PLAYER", payload.get("player_visual_state"))
    for r in rows:
        print(f"SHOT {r['name']:<8} {r['w']}x{r['h']} "
              f"err={r['save_error']} prims={r['prims']:.0f} "
              f"calls={r['draw_calls']:.0f}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("VISUAL_AB_I_OK" if ok else "VISUAL_AB_I_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
