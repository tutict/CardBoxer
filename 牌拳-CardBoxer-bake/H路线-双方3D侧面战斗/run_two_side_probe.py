"""H 路线：同进程同树「双侧 3D」A/B 探针驱动。

把 tests/two_side_probe.gd 复制进游戏工程（新增文件，不改既有），
带窗口跑 Godot 4.5，解析 H2SIDE_JSON payload 并写判据。
用法：python run_two_side_probe.py
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
OUTDIR = HERE / "shots" / "two_side_ab"
LOGS = HERE / "logs"
OUT = HERE / "data" / "two_side_ab.json"
PROBE_SRC = HERE / "tests" / "two_side_probe.gd"
PROBE_DST = GAME / "tests" / "two_side_probe.gd"
PROBE_RES = "res://tests/two_side_probe.gd"


def main() -> int:
    assert GODOT.is_file() and PROBE_SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    PROBE_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROBE_SRC, PROBE_DST)

    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)      # 探针自己挂层，off 阶段必须无 3D
    env["H_2SIDE_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900", "--script", PROBE_RES],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc, text = proc.returncode, (proc.stdout + b"\n--- STDERR ---\n"
                                     + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    (LOGS / "godot_two_side_ab.log").write_text(text, encoding="utf-8")

    marker = "H2SIDE_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = payload.get("shots", [])
    has_gl = "OpenGL API" in text
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    prims = {r["name"]: r.get("prims_mean", 0.0) for r in rows}

    checks = {
        "rc": rc == 0,
        "has_opengl": has_gl,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "player_layer_ready": payload.get("player_layer_ready") is True,
        "foe_layer_ready": payload.get("foe_layer_ready") is True,
        "five_shots": len(rows) == 5,
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file() for r in rows),
        "bones_13": payload.get("bones") == 13,
        "foe_bones_13": payload.get("foe_bones") == 13,
        "player_frames_applied": int(payload.get(
            "player_frames_applied", 0)) > 0,
        "foe_frames_applied": int(payload.get("foe_frames_applied", 0)) > 0,
        "player_tex_drawn": payload.get("player_tex_drawn") is True,
        "foe_tex_drawn": payload.get("foe_tex_drawn") is True,
        "player_yaw_55": payload.get("player_yaw") == 55.0,
        "foe_yaw_minus55": payload.get("foe_yaw") == -55.0,
        "foe_role": payload.get("foe_role") == "foe",
        "both_overrides": (payload.get("player_override") is True
                           and payload.get("enemy_override") is True),
        "env_not_preset": payload.get("use_3d_env") == "",
        "prims_grew": prims.get("both-stance", 0) > prims.get("off", 0) * 2,
        "probe_in_game": PROBE_DST.is_file(),
        "glb_paths_differ": (bool(payload.get("player_glb_path"))
                             and bool(payload.get("foe_glb_path"))
                             and payload.get("player_glb_path")
                             != payload.get("foe_glb_path")),
        "mesh_names_differ": (bool(payload.get("player_mesh_name"))
                              and bool(payload.get("foe_mesh_name"))
                              and payload.get("player_mesh_name")
                              != payload.get("foe_mesh_name")),
        "sv_not_shared": payload.get("sv_same") is False,
        "tex_not_shared": payload.get("tex_same") is False,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "has_opengl": has_gl,
                "script_errors": errors, "headless": False},
        "payload": payload, "prims": prims,
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} gl={has_gl} errors={errors}")
    print(f"LAYERS player={payload.get('player_layer_ready')} "
          f"foe={payload.get('foe_layer_ready')} "
          f"bones={payload.get('bones')}/{payload.get('foe_bones')} "
          f"yaw={payload.get('player_yaw')}/{payload.get('foe_yaw')}")
    print("DIAG glb=", payload.get("player_glb_path"), "/",
          payload.get("foe_glb_path"),
          " mesh=", payload.get("player_mesh_name"), "/",
          payload.get("foe_mesh_name"),
          " sv_same=", payload.get("sv_same"),
          " tex_same=", payload.get("tex_same"))
    print("MESH_SIG player=", payload.get("player_mesh_sig"))
    print("MESH_SIG foe=   ", payload.get("foe_mesh_sig"))
    for r in rows:
        print(f"SHOT {r['name']:<14} {r['w']}x{r['h']} "
              f"err={r['save_error']} prims={r['prims_mean']:.0f} "
              f"calls={r['draw_calls_mean']:.1f}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("TWO_SIDE_AB_OK" if ok else "TWO_SIDE_AB_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
