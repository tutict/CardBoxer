"""H 路线诊断：单侧隔离渲染，确认每层各自画的是哪个模型。

分别只挂 player 层 / 只挂 foe 层，各渲 5 帧；取 both-stance 帧做对照板。
输出 shots/isolate/{player,foe}/h-both-stance.png、boards/H-单侧隔离对照.png
与 data/isolate_h.json。
用法：python run_isolate_h.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
BASE = HERE / "shots" / "isolate"
LOGS = HERE / "logs"
BOARD = HERE / "boards" / "H-单侧隔离对照.png"
OUT = HERE / "data" / "isolate_h.json"
PROBE_SRC = HERE / "tests" / "two_side_probe.gd"
PROBE_DST = GAME / "tests" / "two_side_probe.gd"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")


def run(only: str) -> dict:
    out = BASE / only
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env["H_2SIDE_DIR"] = str(out)
    env["H_2SIDE_ONLY"] = only
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script", "res://tests/two_side_probe.gd"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (proc.stdout + b"\n--- STDERR ---\n"
            + proc.stderr).decode("utf-8", "replace")
    (LOGS / f"godot_isolate_{only}.log").write_text(text, encoding="utf-8")
    marker = "H2SIDE_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    return {"only": only, "rc": proc.returncode,
            "seconds": round(time.perf_counter() - t0, 3),
            "has_opengl": "OpenGL API" in text,
            "errors": text.count("SCRIPT ERROR") + text.count("Parse Error"),
            "payload": payload,
            "stance_png": str(out / "h-both-stance.png")}


def main() -> int:
    assert GODOT.is_file() and PROBE_SRC.is_file()
    BASE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROBE_SRC, PROBE_DST)
    runs = [run("player"), run("foe")]

    ims = []
    for r in runs:
        p = Path(r["stance_png"])
        assert p.is_file(), p
        ims.append(Image.open(p).convert("RGB"))
    w, h = 640, 360
    pad, label = 18, 34
    canvas = Image.new("RGB", (2 * w + 3 * pad, h + label + 2 * pad),
                       (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 20) if FONT.is_file() \
        else ImageFont.load_default()
    for i, (r, im) in enumerate(zip(runs, ims)):
        x = pad + i * (w + pad)
        canvas.paste(im.resize((w, h), Image.LANCZOS), (x, pad))
        d.text((x + 4, pad + h + 4),
               f"only={r['only']}  rc={r['rc']}  errors={r['errors']}",
               font=f, fill=(160, 225, 205))
    canvas.save(BOARD)

    checks = {}
    for r in runs:
        p = r["payload"]
        checks[f"{r['only']}_rc0"] = r["rc"] == 0
        checks[f"{r['only']}_gl"] = r["has_opengl"]
        checks[f"{r['only']}_no_errors"] = r["errors"] == 0
        checks[f"{r['only']}_marker_only"] = p.get("only") == r["only"]
        if r["only"] == "player":
            checks["player_layer_ready"] = p.get("player_layer_ready") is True
            checks["player_foe_layer_absent"] = (
                p.get("foe_layer_ready") is False)
            checks["player_mesh_is_player"] = (
                p.get("player_mesh_name") == "player_HI_skinned")
        else:
            checks["foe_layer_ready"] = p.get("foe_layer_ready") is True
            checks["foe_player_layer_absent"] = (
                p.get("player_layer_ready") is False)
            checks["foe_mesh_is_foe"] = (
                p.get("foe_mesh_name") == "foe_HI_skinned")
    checks["board_nonempty"] = BOARD.stat().st_size > 10000
    report = {"runs": [{k: v for k, v in r.items() if k != "payload"}
                       | {"payload": r["payload"]} for r in runs],
              "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "board": BOARD.name, "board_bytes": BOARD.stat().st_size,
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in runs:
        p = r["payload"]
        print("RUN", r["only"], f"{r['seconds']}s rc={r['rc']} "
              f"gl={r['has_opengl']} errors={r['errors']}")
        print("   player_ready=", p.get("player_layer_ready"),
              "foe_ready=", p.get("foe_layer_ready"),
              "mesh=", p.get("player_mesh_name"), "/",
              p.get("foe_mesh_name"),
              "glb=", p.get("player_glb_path"), "/",
              p.get("foe_glb_path"))
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("ISOLATE_H_OK" if report["ok"] else "ISOLATE_H_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
