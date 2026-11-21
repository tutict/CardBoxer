"""Pixel evidence for the eight in-engine rhythm frames.

Regions avoid the hand-card strip (y>540) because cards are randomly dealt
per run, and avoid the top HUD (y<280) because banner text differs by mode.
Every check is a measurable pixel count, not an aesthetic judgement.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "evidence_rhythm.json"

FILES = {
    "t000": "节奏帧-t000-起手.png",
    "t048": "节奏帧-t048-命中HIT.png",
    "t072": "节奏帧-t072-停顿后.png",
    "t112": "节奏帧-t112-攻击窗末.png",
    "t140": "节奏帧-t140-淡出.png",
    "t180": "节奏帧-t180-归零.png",
    "draw": "节奏帧-平局无节奏.png",
    "foewin": "节奏帧-对手赢反向.png",
}
LABELS = {
    "t000": "t=0.00 起手  输家已后退 40px / 后仰 9°",
    "t048": "t=0.48 命中  前压 102px + HIT! + 星芒",
    "t072": "t=0.72 停顿尾帧  HIT! 仍在 / 前压 39px",
    "t112": "t=1.12 攻击窗末  位移归零",
    "t140": "t=1.36 settle 淡出",
    "t180": "t=1.76 recover  完全归零",
    "draw": "平局  节奏未激活（P0 对峙）",
    "foewin": "对手赢  方向整体反转",
}
HIT_LABEL = (630, 285, 790, 340)
SPARK = (790, 340, 930, 450)
SPEED = (590, 285, 700, 420)
FIGHTERS = (330, 290, 1000, 540)


def diff_px(a, b, box, threshold=18):
    d = ImageChops.difference(a.crop(box).convert("RGB"),
                              b.crop(box).convert("RGB")).convert("L")
    return sum(d.histogram()[threshold + 1:])


def font(size):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
              r"C:\Windows\Fonts\arial.ttf"):
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main() -> int:
    checks, imgs = {}, {}
    for key, fn in FILES.items():
        p = HERE / fn
        if not p.is_file():
            print("[FAIL] E01_%s missing" % key)
            checks["E01_%s" % key] = False
            continue
        im = Image.open(p).convert("RGB")
        imgs[key] = im
        ok = im.size == (1280, 720) and p.stat().st_size > 100_000
        checks["E01_%s" % key] = ok
        print("[%s] E01_%s size=%s bytes=%d" % (
            "PASS" if ok else "FAIL", key, im.size, p.stat().st_size), flush=True)

    pairs = {}
    for name, box, floor in [
        ("E02_hit_label_present", HIT_LABEL, 100),
        ("E03_spark_present", SPARK, 200),
        ("E04_speed_lines_present", SPEED, 30),
        ("E05_fighter_band_moved", FIGHTERS, 2000),
    ]:
        if "t048" in imgs and "t180" in imgs:
            v = diff_px(imgs["t048"], imgs["t180"], box)
            pairs[name] = {"diff_px": v, "floor": floor}
            checks[name] = v > floor
            print("[%s] %s diff=%d floor=%d" % (
                "PASS" if checks[name] else "FAIL", name, v, floor), flush=True)

    cross = {}
    for a, b in (("t048", "draw"), ("t048", "foewin"),
                 ("t000", "t180"), ("t048", "t072"), ("t072", "t112")):
        if a in imgs and b in imgs:
            cross["%s_vs_%s" % (a, b)] = diff_px(imgs[a], imgs[b], FIGHTERS)
    checks["E06_cross_modes_differ"] = (bool(cross)
                                        and min(cross.values()) > 1500)
    print("[%s] E06_cross_modes_differ min=%d %s" % (
        "PASS" if checks["E06_cross_modes_differ"] else "FAIL",
        min(cross.values()) if cross else -1,
        json.dumps(cross, ensure_ascii=False)), flush=True)

    # 对照板：2 列 x 4 行，缩到 620x349，标题单独一行
    if imgs:
        cw, ch, pad, head = 620, 349, 16, 32
        sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + head) * 4 + pad * 5),
                          (22, 24, 32))
        d = ImageDraw.Draw(sheet)
        f = font(18)
        for i, key in enumerate(FILES):
            if key not in imgs:
                continue
            col, row = i % 2, i // 2
            x = pad + col * (cw + pad)
            y = pad + row * (ch + head + pad)
            d.text((x + 6, y + 3), LABELS[key], font=f, fill=(232, 228, 216))
            sheet.paste(imgs[key].resize((cw, ch), Image.LANCZOS), (x, y + head))
        dest = HERE / "节奏帧-八态对照板.png"
        sheet.save(dest)
        print("saved %s (%d B)" % (dest.name, dest.stat().st_size))

    passed = sum(1 for v in checks.values() if v)
    OUT.write_text(json.dumps({
        "checks": checks, "passed": passed, "total": len(checks),
        "region_diffs": pairs, "cross_diffs": cross,
        "result": "EVIDENCE_RHYTHM_OK" if passed == len(checks)
                  else "EVIDENCE_RHYTHM_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d %s" % (
        passed, len(checks),
        "EVIDENCE_RHYTHM_OK" if passed == len(checks) else "EVIDENCE_RHYTHM_FAILED"))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
