"""真实窗口下验证放大后的屏幕：物理 1600x900 / 逻辑 1280x720 / 等比 1.25。

刻意不传 --resolution，否则命令行会覆盖 project.godot 的窗口设置。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT_JSON = HERE / "window_probe.json"
RESULT = HERE / "window_probe_result.json"


def main() -> int:
    env = dict(os.environ)
    env["CARD_BOXER_WINDOW_JSON"] = str(OUT_JSON)
    cmd = [str(GODOT), "--path", str(GAME), "--quit-after", "120",
           "--script", "res://tests/window_probe.gd"]
    proc = subprocess.run(cmd, env=env, capture_output=True, timeout=120)
    text = (proc.stdout + b"\n" + proc.stderr).decode("utf-8", "replace")
    (HERE / "logs" / "window_probe.log").write_text(
        "CMD %s\n\n%s" % (" ".join(cmd), text), encoding="utf-8")
    if "WINDOW_PROBE_DONE" not in text or not OUT_JSON.is_file():
        print("WINDOW PROBE FAILED")
        print(text[-2000:])
        return 1
    d = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    checks = {
        "physical_1600x900": d["physical"] == [1600, 900],
        "logical_1280x720": d["logical"] == [1280, 720],
        "scale_1_25_both_axes": abs(d["scale_x"] - 1.25) < 1e-9
        and abs(d["scale_y"] - 1.25) < 1e-9,
        "stretch_canvas_items": d["stretch_mode"] == "canvas_items",
        "aspect_keep": d["stretch_aspect"] == "keep",
        "aspect_match_16_9": bool(d["aspect_match"]),
    }
    ok = all(checks.values()) and proc.returncode == 0
    RESULT.write_text(json.dumps({
        "probe": d, "checks": checks,
        "result": "WINDOW_ENLARGED_OK" if ok else "WINDOW_ENLARGED_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("WINDOW physical=%s logical=%s scale=%.2f/%.2f mode=%s aspect=%s"
          % (d["physical"], d["logical"], d["scale_x"], d["scale_y"],
             d["stretch_mode"], d["stretch_aspect"]))
    for k, v in checks.items():
        print("  [%s] %s" % ("PASS" if v else "FAIL", k))
    print("RESULT: %s" % ("WINDOW_ENLARGED_OK" if ok else "WINDOW_ENLARGED_FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
