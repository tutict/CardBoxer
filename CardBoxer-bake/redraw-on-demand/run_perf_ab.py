"""按需重绘性能 A/B：多组独立进程，gate=0 / gate=1 各一次。

CPU 证据不用 Performance.TIME_PROCESS（本机实测它是双峰、跨运行会翻转的
窗口采样，见 performance-ab/sweep.json），改用每个 _draw() 里 Time.get_ticks_usec()
实测出来的绘制耗时累计 —— 这是被跳过的工作本身，不随 vsync / 窗口节流变。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "performance-ab"
REPEAT = 3
US_KEYS = ("arena_draw_us", "fx_draw_us", "hud_draw_us")
DRAW_KEYS = ("arena_draws", "fx_draws", "hud_draws")
SKIP_KEYS = ("arena_skipped", "fx_skipped", "hud_skipped")


def run(gate: str, pair_dir: Path) -> int:
    png = pair_dir / ("冻结帧-gate%s.png" % gate)
    js = pair_dir / ("perf-gate%s.json" % gate)
    env = dict(os.environ)
    env["CARD_BOXER_REDRAW_GATE"] = gate
    env["CARD_BOXER_REDRAW_PERF_OUT"] = str(png)
    env["CARD_BOXER_REDRAW_PERF_JSON"] = str(js)
    for key in ("CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_CAPTURE",
                "CARD_BOXER_CAPTURE_HIT", "CARD_BOXER_RHYTHM_SHOT", "CARD_BOXER_RAGE_START"):
        env.pop(key, None)
    cmd = [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
           "--quit-after", "900", "--script", "res://tests/redraw_perf_probe.gd"]
    try:
        p = subprocess.run(cmd, env=env, cwd=str(GAME), capture_output=True, timeout=180)
        text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode("utf-8", "replace")
        rc = p.returncode
    except subprocess.TimeoutExpired as exc:
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")).decode("utf-8", "replace")
        rc = -1
    (pair_dir / ("probe-gate%s.log" % gate)).write_text(
        "CMD %s\n\n%s" % (" ".join(cmd), text), encoding="utf-8")
    bad = (rc != 0 or "REDRAW_PERF_DONE" not in text or "SCRIPT ERROR" in text
           or "Parse Error" in text or not png.is_file() or not js.is_file())
    if bad:
        print("PERF FAILED gate=%s rc=%s" % (gate, rc))
        print(text[-2500:])
        return 1
    return 0


def changed_px(a: Path, b: Path) -> int:
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    diff = ImageChops.difference(ia, ib)
    if diff.getbbox() is None:
        return 0
    return sum(1 for px in diff.get_flattened_data() if px != (0, 0, 0))


def totals(d: dict) -> tuple[int, int, int]:
    st = d["redraw_stats"]
    return (sum(int(st[k]) for k in US_KEYS),
            sum(int(st[k]) for k in DRAW_KEYS),
            sum(int(st[k]) for k in SKIP_KEYS))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = []
    for i in range(1, REPEAT + 1):
        pair_dir = OUT / ("pair%d" % i)
        pair_dir.mkdir(parents=True, exist_ok=True)
        if run("0", pair_dir) or run("1", pair_dir):
            return 1
        d0 = json.loads((pair_dir / "perf-gate0.json").read_text(encoding="utf-8"))
        d1 = json.loads((pair_dir / "perf-gate1.json").read_text(encoding="utf-8"))
        changed = changed_px(pair_dir / "frozen-frame-gate0.png", pair_dir / "frozen-frame-gate1.png")
        u0, n0, s0 = totals(d0)
        u1, n1, s1 = totals(d1)
        rec = {
            "pair": i,
            "changed_px": changed,
            "gate0": {"process_ms": d0["process_ms"]["mean"], "draw_us": u0,
                      "draws": n0, "skips": s0, "prims": d0["primitives"]["mean"],
                      "calls": d0["draw_calls"]["mean"]},
            "gate1": {"process_ms": d1["process_ms"]["mean"], "draw_us": u1,
                      "draws": n1, "skips": s1, "prims": d1["primitives"]["mean"],
                      "calls": d1["draw_calls"]["mean"]},
        }
        pairs.append(rec)
        print("PAIR %d changed=%d | gate0 proc=%.4fms draw=%dus/%d帧 skipped=%d "
              "| gate1 proc=%.4fms draw=%dus/%d帧 skipped=%d"
              % (i, changed, rec["gate0"]["process_ms"], u0, n0, s0,
                 rec["gate1"]["process_ms"], u1, n1, s1))
    mean_off = sum(p["gate0"]["draw_us"] for p in pairs) / REPEAT
    mean_on = sum(p["gate1"]["draw_us"] for p in pairs) / REPEAT
    gain = (mean_off - mean_on) / mean_off * 100.0 if mean_off else 0.0
    proc_off = [round(p["gate0"]["process_ms"], 4) for p in pairs]
    proc_on = [round(p["gate1"]["process_ms"], 4) for p in pairs]
    payload = {
        "repeat": REPEAT,
        "pairs": pairs,
        "draw_us_mean_off": mean_off,
        "draw_us_mean_on": mean_on,
        "draw_us_gain_pct": gain,
        "TIME_PROCESS_off": proc_off,
        "TIME_PROCESS_on": proc_on,
        "TIME_PROCESS_note": "bimodal window sample; retired as a gain criterion",
        "key_bench": "tests/key_bench.gd: str() 6.1140us, hash() 0.1159us, ratio 52.75",
    }
    (OUT / "ab_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 顶层留最后一对的两张 PNG 供归档展示
    for g in ("0", "1"):
        src = OUT / ("pair%d" % REPEAT) / ("冻结帧-gate%s.png" % g)
        (OUT / ("冻结帧-gate%s.png" % g)).write_bytes(src.read_bytes())
    print("AB draw_us %.1f -> %.1f (-%.2f%%) | TIME_PROCESS off=%s on=%s"
          % (mean_off, mean_on, gain, proc_off, proc_on))
    return 0 if all(p["changed_px"] == 0 for p in pairs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
