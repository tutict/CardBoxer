"""I 路线收口：I 改动后「默认关」与 G 改动前基线工程逐像素等价。

基线工程复用 G 路线 baseline_project（G 改动前的完整 2D 工程副本）。
不设 CARD_BOXER_3D 时 I 的双轨开关不创建任何 3D 层，因此**默认关
零污染**；跨进程整帧不可比已被 H 路线退役，这里只用 perf_probe.gd
冻结静态状态 120 帧的可复现通道。用法：python run_static_ab_i.py
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BASE_PROJECT = (HERE.parent / "G路线-游戏内3D接线" / "baseline_project")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "data" / "static_ab_i.json"
LOGS = HERE / "logs"
SHOTS = HERE / "shots" / "static_ab_i"
PROBE = "res://tests/perf_probe.gd"


def run(project: Path, tag: str) -> dict:
    d = SHOTS / tag
    d.mkdir(parents=True, exist_ok=True)
    png = d / "背景基线.png"
    js = d / "perf.json"
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_FOE_VISUAL", None)
    env["CARD_BOXER_PERF_OUT"] = str(png)
    env["CARD_BOXER_PERF_JSON"] = str(js)
    env["CARD_BOXER_PERF_FRAMES"] = "120"
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(project),
             "--resolution", "1280x720", "--quit-after", "900",
             "--script", PROBE],
            env=env, capture_output=True, timeout=240, cwd=str(project))
        rc = proc.returncode
        text = (proc.stdout + b"\n--- STDERR ---\n"
                + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    (LOGS / ("static_ab_i_%s.log" % tag)).write_text(text, encoding="utf-8")
    perf = json.loads(js.read_text(encoding="utf-8")) if js.is_file() else {}
    return {"tag": tag, "project": str(project), "rc": rc, "seconds": dt,
            "png": png, "perf": perf,
            "marker": "PERF_PROBE_DONE" in text,
            "errors": text.count("SCRIPT ERROR") + text.count("Parse Error"),
            "has_opengl": "OpenGL API" in text}


def main() -> int:
    assert BASE_PROJECT.is_dir(), BASE_PROJECT
    LOGS.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    a = run(BASE_PROJECT, "pre_g_baseline")
    b = run(GAME, "i_off")

    ia = Image.open(a["png"]).convert("RGB") if a["png"].is_file() else None
    ib = Image.open(b["png"]).convert("RGB") if b["png"].is_file() else None
    changed = None
    if ia is not None and ib is not None and ia.size == ib.size:
        changed = sum(ImageChops.difference(ia, ib)
                      .convert("L").histogram()[1:])
    checks = {
        "both_rc0": a["rc"] == 0 and b["rc"] == 0,
        "both_markers": a["marker"] and b["marker"],
        "both_gl": a["has_opengl"] and b["has_opengl"],
        "no_errors": a["errors"] == 0 and b["errors"] == 0,
        "both_png": ia is not None and ib is not None,
        "same_size": ia is not None and ib is not None and ia.size == ib.size,
        "pixel_identical": changed == 0,
        "same_sample_count": a["perf"].get("samples") == 120
                             and b["perf"].get("samples") == 120,
        "same_viewport": a["perf"].get("viewport") == [1280, 720]
                         and b["perf"].get("viewport") == [1280, 720],
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "baseline_project": str(BASE_PROJECT),
        "baseline": {k: (str(v) if isinstance(v, Path) else v)
                     for k, v in a.items()},
        "i_off": {k: (str(v) if isinstance(v, Path) else v)
                  for k, v in b.items()},
        "changed_pixels": changed,
        "prims_mean": {"baseline": a["perf"].get("primitives", {}).get("mean"),
                       "i_off": b["perf"].get("primitives", {}).get("mean")},
        "draw_calls_mean": {
            "baseline": a["perf"].get("draw_calls", {}).get("mean"),
            "i_off": b["perf"].get("draw_calls", {}).get("mean")},
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BASELINE rc={a['rc']} {a['seconds']}s  "
          f"I_OFF rc={b['rc']} {b['seconds']}s")
    print(f"CHANGED_PIXELS={changed}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("STATIC_AB_I_OK" if ok else "STATIC_AB_I_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
