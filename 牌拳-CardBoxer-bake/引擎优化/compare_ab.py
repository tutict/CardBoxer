"""优化前/后 A/B：逐像素等价 + 引擎帧统计对比 + 对照板。

像素等价是硬门槛：差异像素数必须为 0，否则优化改变了画面，判据失败。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
RESULT = HERE / "ab_result.json"
BOARD = HERE / "引擎优化-AB对照.png"


def metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(before: float, after: float) -> float:
    return (after - before) / before * 100.0 if before else 0.0


def main() -> int:
    a_png = HERE / "baseline" / "背景基线.png"
    b_png = HERE / "after" / "背景基线.png"
    a = Image.open(a_png).convert("RGB")
    b = Image.open(b_png).convert("RGB")
    diff = ImageChops.difference(a, b)
    hist = diff.convert("L").histogram()
    changed = sum(hist[1:])
    extrema = diff.getextrema()
    same_size = a.size == b.size
    pixel_identical = same_size and changed == 0

    before = metrics(HERE / "baseline" / "perf.json")
    after = metrics(HERE / "after" / "perf.json")
    keys = ["process_ms", "primitives", "draw_calls"]
    deltas = {}
    for k in keys:
        x, y = before[k]["mean"], after[k]["mean"]
        deltas[k] = {"before": x, "after": y, "delta": y - x,
                     "pct": pct(x, y)}
    # 采样必须同为 120 帧、同视口、且两次 primitives 都逐帧恒定
    comparable = (before["samples"] == after["samples"] == 120
                  and before["viewport"] == after["viewport"] == [1280, 720]
                  and before["warmup"] == after["warmup"]
                  and len(set(before["raw_primitives"])) == 1
                  and len(set(after["raw_primitives"])) == 1)

    ok = pixel_identical and comparable and all(
        deltas[k]["delta"] < 0 for k in ("primitives", "draw_calls"))
    RESULT.write_text(json.dumps({
        "before_bytes": a_png.stat().st_size, "after_bytes": b_png.stat().st_size,
        "size": list(a.size), "changed_pixels": changed,
        "diff_extrema": [list(x) for x in extrema],
        "pixel_identical": pixel_identical,
        "comparable": comparable, "deltas": deltas,
        "result": "ENGINE_OPT_AB_OK" if ok else "ENGINE_OPT_AB_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 对照板：左基线 / 右优化后 / 右下角数字栏，中间不拉伸。
    scale = 0.5
    tw, th = int(a.width * scale), int(a.height * scale)
    board = Image.new("RGB", (tw * 2 + 18, th + 92), (18, 20, 28))
    board.paste(a.resize((tw, th)), (0, 0))
    board.paste(b.resize((tw, th)), (tw + 18, 0))
    dr = ImageDraw.Draw(board)
    lines = [
        "BEFORE  primitives %.0f  draw_calls %.0f  process %.3f ms" % (
            deltas["primitives"]["before"], deltas["draw_calls"]["before"],
            deltas["process_ms"]["before"]),
        "AFTER   primitives %.0f  draw_calls %.0f  process %.3f ms" % (
            deltas["primitives"]["after"], deltas["draw_calls"]["after"],
            deltas["process_ms"]["after"]),
        "DELTA   primitives %+.0f (%.1f%%)   draw_calls %+.0f   process %+.3f ms (%.1f%%)" % (
            deltas["primitives"]["delta"], deltas["primitives"]["pct"],
            deltas["draw_calls"]["delta"], deltas["process_ms"]["delta"],
            deltas["process_ms"]["pct"]),
        "PIXELS  changed=%d  identical=%s  (1280x720, same-state frozen frame)" % (
            changed, pixel_identical),
    ]
    for i, line in enumerate(lines):
        dr.text((10, th + 10 + i * 20), line, fill=(225, 230, 240))
    board.save(BOARD)

    print("PIXEL changed=%d identical=%s bytes=%d/%d extrema=%s"
          % (changed, pixel_identical, a_png.stat().st_size,
             b_png.stat().st_size, extrema))
    for k in keys:
        d = deltas[k]
        print("%-12s %10.4f -> %10.4f  delta=%+.4f (%+.1f%%)"
              % (k, d["before"], d["after"], d["delta"], d["pct"]))
    print("RESULT: %s" % ("ENGINE_OPT_AB_OK" if ok else "ENGINE_OPT_AB_FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
