"""止损诊断：同一台机器上按两种启动方式各截一帧完整主场景画面。

case default = play-2d.bat 的真实环境（没有 CARD_BOXER_3D）
case 3d      = 显式打开 3D 表现层
两帧都保留 HUD / fx / World，不隐藏任何层。
用法：python run_display_probe.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
PROBE = "res://tests/display_stopgap_probe.gd"
CLEAR_ENV = (
    "CARD_BOXER_3D", "CARD_BOXER_FOE_VISUAL", "CARD_BOXER_3D_STANCE",
    "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
)
CASES = [("default", {}), ("3d", {"CARD_BOXER_3D": "1"})]
# 第一轮（B round2 还在工程里）用 tag before；回滚后复测用 tag after。
TAG = sys.argv[1] if len(sys.argv) > 1 else "after"


def run(name: str, extra: dict[str, str]) -> dict:
    out_dir = HERE / "shots" / f"{TAG}-{name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (HERE / "logs").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in CLEAR_ENV:
        env.pop(k, None)
    env.update(extra)
    env["DISPLAY_DIR"] = str(out_dir)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script", PROBE],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    dt = round(time.perf_counter() - t0, 3)
    text = (proc.stdout + b"\n--- STDERR ---\n" + proc.stderr).decode(
        "utf-8", "replace")
    (HERE / "logs" / f"godot_{TAG}_{name}.out").write_text(
        text, encoding="utf-8")
    marker = "DISPLAY_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    result = {
        "case": name, "seconds": dt, "returncode": proc.returncode,
        "script_errors": text.count("SCRIPT ERROR") + text.count("Parse Error"),
        "has_opengl": "OpenGL API" in text,
        "payload": payload,
        "pngs": sorted(str(p) for p in out_dir.glob("*.png")),
    }
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CASE {name} {dt}s rc={proc.returncode} "
          f"errors={result['script_errors']} pngs={len(result['pngs'])}")
    print("  payload " + json.dumps(payload, ensure_ascii=False))
    return result


def main() -> int:
    assert GODOT.is_file(), GODOT
    assert (GAME / PROBE.replace("res://", "")).is_file()
    results = [run(n, e) for n, e in CASES]
    ok = all(
        r["returncode"] == 0 and r["script_errors"] == 0
        and len(r["pngs"]) == 2 and "error" not in r["payload"]
        for r in results)
    print("DISPLAY_PROBE_OK" if ok else "DISPLAY_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
