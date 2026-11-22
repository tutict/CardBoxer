"""Pixel evidence for the five in-engine P0 wiring frames.

No OCR, no guesswork: assert on measurable pixel facts only.
  * every frame is a real 1280x720 non-blank render
  * the HUD hint strip (y=695..720) must DIFFER between triple / sequence /
    scatter / draw -> the motion label is actually drawn, not dead code
  * the upper banner strip (y=20..130) must differ between reveal and resolve
  * the fighter band (y=250..600) must differ between jab and wave frames
  * write a 2x3 contact sheet for human review
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "evidence_p0.json"

FILES = {
    "reveal": "engine-frames-reveal-focus.png",
    "triple": "engine-frames-triple-wave.png",
    "sequence": "engine-frames-straight-cross-counter.png",
    "scatter": "engine-frames-scatter-jab.png",
    "draw": "engine-frames-draw-standoff.png",
}
LABELS = {
    "reveal": "亮牌 phase=reveal  双方 focus  100/100",
    "triple": "三同 999  wave 气功波  -23",
    "sequence": "三连 456  cross 交叉反击  -15",
    "scatter": "散牌 258  jab 刺拳  -10",
    "draw": "平局 对峙  双方各 -3",
}
HINT = (44, 692, 1100, 720)
BANNER = (240, 20, 1040, 130)
FIGHTERS = (180, 250, 1100, 600)


def diff_px(a: Image.Image, b: Image.Image, box, threshold=18) -> int:
    d = ImageChops.difference(a.crop(box).convert("RGB"),
                              b.crop(box).convert("RGB")).convert("L")
    return sum(d.histogram()[threshold + 1:])


def font(size: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
              r"C:\Windows\Fonts\arial.ttf"):
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main() -> int:
    imgs = {}
    checks = {}

    def check(name, ok, detail):
        checks[name] = {"ok": bool(ok), "detail": detail}
        print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    for key, fn in FILES.items():
        p = HERE / fn
        if not p.is_file():
            check("E01_frame_exists_%s" % key, False, "missing " + fn)
            continue
        im = Image.open(p).convert("RGB")
        imgs[key] = im
        non_blank = len(im.getcolors(maxcolors=1 << 24) or []) > 64
        check("E01_frame_%s" % key,
              im.size == (1280, 720) and p.stat().st_size > 100_000 and non_blank,
              "size=%s bytes=%d colors>64=%s" % (im.size, p.stat().st_size, non_blank))

    # HUD 提示行：四种 resolve 牌型两两不同 => 招式名真的画出来了
    hint_diffs = {}
    for a, b in (("triple", "sequence"), ("triple", "scatter"),
                 ("triple", "draw"), ("sequence", "scatter"),
                 ("sequence", "draw"), ("scatter", "draw")):
        if a in imgs and b in imgs:
            hint_diffs["%s_vs_%s" % (a, b)] = diff_px(imgs[a], imgs[b], HINT)
    check("E02_hint_strip_differs",
          bool(hint_diffs) and min(hint_diffs.values()) > 20,
          "min=%d pairs=%s" % (min(hint_diffs.values()) if hint_diffs else -1,
                               json.dumps(hint_diffs, ensure_ascii=False)))

    # 亮牌 vs 结算：banner 区不同，说明阶段文案确实换了
    banner_diff = (diff_px(imgs["reveal"], imgs["triple"], BANNER)
                   if "reveal" in imgs and "triple" in imgs else -1)
    check("E03_banner_reveal_vs_resolve", banner_diff > 200,
          "diff_px=%d" % banner_diff)

    # 角色带：jab 与 wave 的动作帧不同，不只是文字变了
    fighter_pairs = {}
    for a, b in (("triple", "scatter"), ("triple", "sequence"),
                 ("sequence", "scatter"), ("triple", "draw")):
        if a in imgs and b in imgs:
            fighter_pairs["%s_vs_%s" % (a, b)] = diff_px(imgs[a], imgs[b], FIGHTERS)
    check("E04_fighter_band_differs",
          bool(fighter_pairs) and min(fighter_pairs.values()) > 100,
          "min=%d pairs=%s" % (min(fighter_pairs.values()) if fighter_pairs else -1,
                               json.dumps(fighter_pairs, ensure_ascii=False)))

    # 亮牌帧不能掉血：日志已证 hp=100/100，这里再钉「亮牌帧与任一结算帧不同」
    reveal_vs_all = {k: diff_px(imgs["reveal"], imgs[k], (0, 0, 1280, 720))
                     for k in ("triple", "sequence", "scatter", "draw")
                     if k in imgs and "reveal" in imgs}
    check("E05_reveal_is_distinct_stage",
          bool(reveal_vs_all) and min(reveal_vs_all.values()) > 5000,
          json.dumps(reveal_vs_all, ensure_ascii=False))

    # 对照板：2 列 x 3 行，缩到 620x349，右侧留一行标题
    if imgs:
        cw, ch, pad, head = 640, 360, 16, 34
        sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + head) * 3 + pad * 4),
                          (24, 26, 34))
        d = ImageDraw.Draw(sheet)
        f = font(19)
        order = ["reveal", "triple", "sequence", "scatter", "draw"]
        for i, key in enumerate(order):
            if key not in imgs:
                continue
            col, row = i % 2, i // 2
            x = pad + col * (cw + pad)
            y = pad + row * (ch + head + pad)
            d.text((x + 6, y + 4), LABELS[key], font=f, fill=(235, 232, 220))
            sheet.paste(imgs[key].resize((cw, ch), Image.LANCZOS), (x, y + head))
        dest = HERE / "engine-frames-five-state-board.png"
        sheet.save(dest)
        print("saved %s (%d B)" % (dest.name, dest.stat().st_size))

    passed = sum(1 for c in checks.values() if c["ok"])
    OUT.write_text(json.dumps({
        "checks": checks, "passed": passed, "total": len(checks),
        "hint_diffs": hint_diffs, "banner_diff": banner_diff,
        "fighter_pairs": fighter_pairs, "reveal_vs_all": reveal_vs_all,
        "result": "EVIDENCE_P0_OK" if passed == len(checks) else "EVIDENCE_P0_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d %s" % (passed, len(checks),
                                "EVIDENCE_P0_OK" if passed == len(checks) else "EVIDENCE_P0_FAILED"))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
