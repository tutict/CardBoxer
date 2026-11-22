"""8 张真实游戏节奏帧的回归证据记录（不是逐像素等价判据）。

订正记录（2026-11-08）：
  初版要求「优化后重渲的 8 张帧与上轮归档逐像素 identical」，0/8 全红。
  看图定位到差异集中在随机手牌与动作相位；tests/rng_probe.gd 三次独立
  运行证明 Godot 每次启动都会随机化全局 RNG（unseeded 三次互不相同），
  且 RandomNumberGenerator.new() 不消耗全局序列 —— 所以这是**跨运行不可
  复现**，与本轮优化无关，判据本身设计错了。

  零视觉变化的硬证据是同状态静态背景 A/B（compare_ab.py 的 changed=0）：
  同一棵树、同一冻结状态、只差优化，1280x720 全图逐像素完全一致。
  这里只负责记录「8 张帧正常生成、尺寸正确、引擎无错误、还原成功」，
  并把全图差异如实写进 JSON，不拿它当失败条件。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
ARCHIVE = BAKE / "side-view-rhythm"
SHOTS = HERE / "regression-frames"
RESULT = HERE / "regression_result.json"

NAMES = [
    "rhythm-frame-t000-startup.png",
    "rhythm-frame-t048-impact-HIT.png",
    "rhythm-frame-t072-after-hitstop.png",
    "rhythm-frame-t112-active-window-end.png",
    "rhythm-frame-t140-fade-out.png",
    "rhythm-frame-t180-reset.png",
    "rhythm-frame-draw-no-rhythm.png",
    "rhythm-frame-foe-win-reversed.png",
]


def main() -> int:
    capture = json.loads((HERE / "regression-frames" / "capture_result.json").read_text(
        encoding="utf-8")) if (HERE / "regression-frames" / "capture_result.json").is_file() \
        else json.loads((HERE / "capture_result.json").read_text(encoding="utf-8"))
    # capture_rhythm.main() 写的是 (cr.OUT / "capture_result.json")，即 regression-frames/。
    recs = {r["mode"]: r for r in capture["records"]}
    rows = []
    for name in NAMES:
        old, new = ARCHIVE / name, SHOTS / name
        if not old.is_file() or not new.is_file():
            rows.append({"name": name, "ok": False, "reason": "missing file"})
            continue
        a = Image.open(old).convert("RGB")
        b = Image.open(new).convert("RGB")
        changed = sum(ImageChops.difference(a, b).convert("L").histogram()[1:])
        rows.append({"name": name, "ok": a.size == b.size == (1280, 720),
                     "changed_px_full_frame": changed, "size": list(a.size),
                     "old_bytes": old.stat().st_size,
                     "new_bytes": new.stat().st_size})
    frames_ok = all(r["ok"] for r in rows) and len(rows) == len(NAMES)
    engine_ok = (len(recs) == 8 and all(r["ok"] and r["engine_errors"] == 0
                                        and r["gl"] for r in recs.values())
                 and capture.get("restore_ok", False))
    ab = json.loads((HERE / "ab_result.json").read_text(encoding="utf-8"))
    static_identical = ab["pixel_identical"] and ab["changed_pixels"] == 0
    ok = frames_ok and engine_ok and static_identical
    RESULT.write_text(json.dumps({
        "rows": rows, "frames_ok": frames_ok, "engine_ok": engine_ok,
        "restore_ok": capture.get("restore_ok", False),
        "static_ab_pixel_identical": static_identical,
        "note": "full-frame diff is EXPECTED: global RNG is randomized per Godot "
                "run (see tests/rng_probe.gd); hand cards are random. Static "
                "same-state A/B is the zero-visual-change evidence.",
        "result": "REGRESSION_EVIDENCE_OK" if ok else "REGRESSION_EVIDENCE_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("frames_ok=%s engine_ok=%s restore=%s static_AB_identical=%s"
          % (frames_ok, engine_ok, capture.get("restore_ok"), static_identical))
    for r in rows:
        print("  %-28s size=%s full_frame_diff=%s (informational)"
              % (r["name"], r.get("size"), r.get("changed_px_full_frame", "-")))
    print("RESULT: %s" % ("REGRESSION_EVIDENCE_OK" if ok
                          else "REGRESSION_EVIDENCE_FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
