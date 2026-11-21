"""临时烟测：跑某个 GDScript 自检，带超时并落日志。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
HERE = Path(__file__).resolve().parent

script = sys.argv[1] if len(sys.argv) > 1 else "res://tests/redraw_gate_check.gd"
headless = "--headless" if len(sys.argv) < 3 or sys.argv[2] != "gl" else ""
cmd = [str(GODOT)]
if headless:
    cmd.append(headless)
cmd += ["--path", str(GAME), "--script", script]
try:
    p = subprocess.run(cmd, capture_output=True, timeout=60)
    text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode("utf-8", "replace")
    rc = p.returncode
except subprocess.TimeoutExpired as e:
    text = ((e.stdout or b"") + b"\n--- TIMEOUT ---\n" + (e.stderr or b"")).decode("utf-8", "replace")
    rc = -1
(HERE / "logs" / "smoke.log").write_text(text, encoding="utf-8")
print("RC=%d" % rc)
print(text[-4000:])
