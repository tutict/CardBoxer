"""G 路线：反向/混合符号的站架偏置扫描，候选从 JSON 注入，不覆盖首轮证据。

用法：python run_side_stance_scan.py
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUTDIR = HERE / "shots" / "side_stance_scan"
LOGS = HERE / "logs"
OUT = HERE / "data" / "side_stance_scan.json"

# 首轮 b1/b2/b3 把双臂收了但拳落在腰前；这里扫反号与拆分组合，
# 目标是「拳到下颌前」且网格不撕裂。f=前手(画面右)，b=后手。
CASES = [
    {"name": "r0-flip-all", "bias": {
        "upperarm_f": 26.0, "forearm_f": -50.0,
        "upperarm_b": -26.0, "forearm_b": 50.0,
        "spine": 4.0, "head": -2.4,
        "thigh_f": 10.0, "shin_f": -6.0,
        "thigh_b": -12.0, "shin_b": 7.0}},
    {"name": "r1-flip-fore", "bias": {
        "upperarm_f": -26.0, "forearm_f": -50.0,
        "upperarm_b": 26.0, "forearm_b": 50.0,
        "thigh_f": 10.0, "shin_f": -6.0,
        "thigh_b": -12.0, "shin_b": 7.0}},
    {"name": "r2-flip-upper", "bias": {
        "upperarm_f": 26.0, "forearm_f": 50.0,
        "upperarm_b": -26.0, "forearm_b": -50.0,
        "thigh_f": 10.0, "shin_f": -6.0,
        "thigh_b": -12.0, "shin_b": 7.0}},
    {"name": "r3-fonly-neg", "bias": {
        "upperarm_f": -26.0, "forearm_f": -50.0,
        "upperarm_b": 26.0, "forearm_b": -50.0,
        "thigh_f": 10.0, "shin_f": -6.0,
        "thigh_b": -12.0, "shin_b": 7.0}},
    {"name": "r4-both-neg", "bias": {
        "upperarm_f": -26.0, "forearm_f": -50.0,
        "upperarm_b": -26.0, "forearm_b": -50.0,
        "thigh_f": 10.0, "shin_f": -6.0,
        "thigh_b": -12.0, "shin_b": 7.0}},
    {"name": "r5-guard-high", "bias": {
        "upperarm_f": -34.0, "forearm_f": -62.0,
        "upperarm_b": -34.0, "forearm_b": -62.0,
        "spine": 4.0, "head": -2.4,
        "thigh_f": 10.0, "shin_f": -6.0,
        "thigh_b": -12.0, "shin_b": 7.0}},
]


def main() -> int:
    assert GODOT.is_file(), GODOT
    OUTDIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP"):
        env.pop(k, None)
    env["G_STANCE_DIR"] = str(OUTDIR)
    env["G_STANCE_CASES"] = json.dumps(CASES, ensure_ascii=False)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "1400",
             "--script", "res://tests/side_stance_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc, text = proc.returncode, (proc.stdout + b"\n--- STDERR ---\n"
                                     + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    (LOGS / "godot_side_stance_scan.log").write_text(text, encoding="utf-8")

    marker = "G_STANCE_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = payload.get("shots", [])
    has_gl = "OpenGL API" in text
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    checks = {
        "rc": rc == 0, "has_opengl": has_gl,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "layer_ready": payload.get("layer_ready") is True,
        "six_cases": len(rows) == len(CASES),
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file() for r in rows),
        "cases_injected": payload.get("cases_count") == len(CASES),
        "bones_13": payload.get("bones") == 13,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc, "has_opengl": has_gl,
                "script_errors": errors, "headless": False},
        "cases": CASES, "payload": payload,
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} gl={has_gl} errors={errors}")
    print(f"LAYER ready={payload.get('layer_ready')} "
          f"cases={payload.get('cases_count')} bones={payload.get('bones')}")
    for r in rows:
        print(f"SHOT {r['name']:<16} {r['w']}x{r['h']} err={r['save_error']}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("SIDE_STANCE_SCAN_OK" if ok else "SIDE_STANCE_SCAN_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
