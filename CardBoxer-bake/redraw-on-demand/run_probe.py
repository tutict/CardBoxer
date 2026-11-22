"""跑一次真实 GL 窗口的静止帧 A/B 探针。

同一进程内五段相位，只切 arena.redraw_gate_enabled，避免跨运行全局 RNG
造成手牌不同（engine-optimization/ 已踩过这个坑）。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "comparison-frames"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (HERE / "logs").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CARD_BOXER_REDRAW_OUT"] = str(OUT)
    # 关掉其它注入/自动对战钩子，保证注入态是唯一变量
    for key in ("CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_TK_SHOT",
                "CARD_BOXER_P0_SHOT", "CARD_BOXER_CAPTURE", "CARD_BOXER_CAPTURE_HIT",
                "CARD_BOXER_RHYTHM_SHOT", "CARD_BOXER_RAGE_START"):
        env.pop(key, None)
    cmd = [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
           "--quit-after", "2000", "--script", "res://tests/redraw_probe.gd"]
    try:
        p = subprocess.run(cmd, env=env, cwd=str(GAME), capture_output=True, timeout=240)
        text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode("utf-8", "replace")
        rc = p.returncode
    except subprocess.TimeoutExpired as exc:
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")).decode("utf-8", "replace")
        rc = -1
    (HERE / "logs" / "probe.log").write_text("CMD %s\n\n%s" % (" ".join(cmd), text), encoding="utf-8")
    result = OUT / "probe_result.json"
    bad = (rc != 0 or "REDRAW_PROBE_DONE" not in text or "SCRIPT ERROR" in text
           or "Parse Error" in text or not result.is_file())
    if bad:
        print("PROBE FAILED rc=%s" % rc)
        print(text[-3000:])
        return 1
    data = json.loads(result.read_text(encoding="utf-8"))
    for ph in data["phases"]:
        d = ph["redraw_delta"]
        print("%-12s gate=%-5s proc_ms=%.5f  arena_draws=%-3d fx_draws=%-3d hud_draws=%-3d skipped=%d"
              % (ph["name"], ph["gate"], ph["process_ms"]["mean"],
                 d["arena_draws"], d["fx_draws"], d["hud_draws"], d["arena_skipped"]))
    print("PROBE OK phases=%d" % len(data["phases"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
