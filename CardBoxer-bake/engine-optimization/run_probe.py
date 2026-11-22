"""跑一次引擎内 perf_probe.gd，把 PNG 与 JSON 落到指定 phase 目录。

用法： python run_probe.py baseline | after
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
PROBE = "res://tests/perf_probe.gd"


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if phase not in ("baseline", "after"):
        print("PHASE must be baseline|after")
        return 2
    out = HERE / phase
    out.mkdir(parents=True, exist_ok=True)
    png = out / "background-baseline.png"
    js = out / "perf.json"
    log = HERE / "logs" / ("probe_%s.log" % phase)
    log.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["CARD_BOXER_PERF_OUT"] = str(png)
    env["CARD_BOXER_PERF_JSON"] = str(js)
    env["CARD_BOXER_PERF_FRAMES"] = "120"
    cmd = [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
           "--quit-after", "900", "--script", PROBE]
    proc = subprocess.run(cmd, env=env, capture_output=True, timeout=180)
    text = (proc.stdout + b"\n" + proc.stderr).decode("utf-8", "replace")
    log.write_text("CMD %s\n\n%s" % (" ".join(cmd), text), encoding="utf-8")

    bad = ("SCRIPT ERROR" in text or "Parse Error" in text
           or "PERF_PROBE_DONE" not in text or proc.returncode != 0
           or not png.is_file() or not js.is_file())
    if bad:
        print("PROBE FAILED phase=%s rc=%s" % (phase, proc.returncode))
        print(text[-2500:])
        return 1
    d = json.loads(js.read_text(encoding="utf-8"))
    print("PROBE OK phase=%s viewport=%s samples=%d prims_mean=%.2f calls_mean=%.2f proc_ms=%.5f png=%dB"
          % (phase, d["viewport"], d["samples"], d["primitives"]["mean"],
             d["draw_calls"]["mean"], d["process_ms"]["mean"], png.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
